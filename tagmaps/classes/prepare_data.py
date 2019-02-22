# -*- coding: utf-8 -*-

"""Module for preparing base data and calculating
overall statistics.

Returns:
    PreparedStats: Statistics prepared for Tag Maps clustering
    self.cleaned_post_dict: Cleaned list of posts
"""


import sys
import os
import ntpath
import csv
import logging
from pathlib import Path
from glob import glob
from _csv import QUOTE_MINIMAL
from decimal import Decimal
import json
import math
import collections
from typing import (
    Type, List, Set, Dict, Tuple, Optional,
    TextIO, Union, DefaultDict, NamedTuple, Counter as CDict)
from collections import Counter
from collections import defaultdict
from collections import namedtuple

from shapely.geometry import Polygon
from shapely.geometry import shape
from shapely.geometry import Point
from tagmaps.classes.utils import Utils
from tagmaps.classes.shared_structure import (
    EMOJI, LOCATIONS, TAGS, TOPICS, ClusterType)
from tagmaps.classes.shared_structure import (
    PostStructure, CleanedPost, AnalysisBounds)


class PrepareData():
    """Main Class for building summary statistics.

    - will process individual cleaned post data into dict/set structures
    - will filter data, cleaned output can be stored
    - will generate statistics
    """

    def __init__(
            self, cluster_types, write_cleaned_data, max_items,
            output_folder, remove_long_tail, limit_bottom_user_count,
            topic_modeling):
        """Initializes Prepare Data structure"""
        # global settings
        self.cluster_types = cluster_types
        self.write_cleaned_data = write_cleaned_data
        self.max_items = max_items
        self.output_folder = output_folder
        self.remove_long_tail = remove_long_tail
        self.limit_bottom_user_count = limit_bottom_user_count
        self.topic_modeling = topic_modeling
        # global vars
        self.count_glob = 0
        self.bounds = AnalysisBounds()
        self.log = logging.getLogger("tagmaps")
        # The following dict stores, per cls_type,
        # the total number of times items appeared
        # these are used to measure total counts
        self.total_item_counter: Dict[ClusterType, CDict] = dict()
        for cls_type in self.cluster_types:
            self.total_item_counter[cls_type] = collections.Counter()
        #self.total_tag_counter = collections.Counter()
        #self.total_emoji_counter = collections.Counter()
        #self.total_location_counter = collections.Counter()
        self.cleaned_stats: Dict[ClusterType, NamedTuple] = dict()
        # Hashsets:
        self.locations_per_userid_dict = defaultdict(set)
        self.userlocation_taglist_dict = defaultdict(set)
        self.userlocation_emojilist_dict = defaultdict(set)
        self.locid_locname_dict: Dict[str, str] = dict()  # nopep8
        if self.topic_modeling:
            self.user_topiclist_dict = defaultdict(set)
            self.user_post_ids_dict = defaultdict(set)
            self.userpost_first_thumb_dict = defaultdict(str)
        self.userlocation_wordlist_dict = defaultdict(set)
        self.userlocations_firstpost_dict = defaultdict(set)
        # UserDict_TagCounters = defaultdict(set)
        # The following dict stores, per cls_type, the distinct items
        # on a per user basis, e.g.
        # self.useritem_counts_global[TAGS][USERGUID] = {term1, term2, term3}
        self.useritem_counts_global:  Dict[
            ClusterType, DefaultDict[str, Set[str]]] = dict()
        for cls_type in self.cluster_types:
            self.useritem_counts_global[cls_type] = defaultdict(set)

        #self.userdict_tagcounters_global = defaultdict(set)
        #self.userdict_emojicounters_global = defaultdict(set)
        #self.userdict_locationcounters_global = defaultdict(set)
        # UserIDsPerLocation_dict = defaultdict(set)
        # PhotoLocDict = defaultdict(set)
        self.distinct_locations_set = set()
        self.distinct_userlocations_set = set()

    def add_record(
            self, lbsn_post: Union[PostStructure, CleanedPost]):
        """Method will merge all tags/emoji/terms
        of a single user for each location (Metric 'UPL') to
        produce a cleaned version of input data


        - further information is derived from the first
        post for each user-location
        - the result is a cleaned output containing
        reduced information that is necessary for tag maps
        - get cleaned output with get_prepared_data()
        """
        self.count_glob += 1
        self._update_toplists(lbsn_post)
        # create userid_loc_id, this is used as the base
        # for clustering data (metric UPL)
        post_locid_userid = f'{lbsn_post.loc_id}::{lbsn_post.user_guid}'
        self.distinct_locations_set.add(lbsn_post.loc_id)
        # print(f'Added: {photo_locID} to distinct_locations_set '
        #       f'(len: {len(self.distinct_locations_set)})')
        self.distinct_userlocations_set.add(post_locid_userid)
        # print(f'Added: {post_locid_userid} to distinct_userlocations_set '
        #       f'(len: {len(distinct_userlocations_set)})')
        # todo:

        if (lbsn_post.loc_name and
                lbsn_post.loc_id not in self.locid_locname_dict):
            # add locname to dict
            self.locid_locname_dict[
                lbsn_post.loc_id] = lbsn_post.loc_name
        if lbsn_post.user_guid not in \
                self.locations_per_userid_dict or \
                lbsn_post.loc_id not in \
                self.locations_per_userid_dict[
                    lbsn_post.user_guid]:
            # Bit wise or and assignment in one step.
            # -> assign locID to UserDict list
            # if not already contained
            self.locations_per_userid_dict[
                lbsn_post.user_guid] |= {
                lbsn_post.loc_id}
            # self.stats.count_loc += 1
            self.userlocations_firstpost_dict[
                post_locid_userid] = lbsn_post

        # union tags/emoji per userid/unique location
        if TAGS in self.cluster_types:
            self.userlocation_taglist_dict[
                post_locid_userid] |= lbsn_post.hashtags
        if EMOJI in self.cluster_types:
            self.userlocation_emojilist_dict[
                post_locid_userid] |= lbsn_post.emoji
        if isinstance(lbsn_post, PostStructure):
            # get cleaned wordlist
            cleaned_wordlist = set(self._get_cleaned_wordlist(
                lbsn_post.post_body))
        else:
            # words already cleaned
            cleaned_wordlist = lbsn_post.post_body
        # union words per userid/unique location
        self.userlocation_wordlist_dict[
            post_locid_userid] |= cleaned_wordlist

    def get_cleaned_post_dict(
            self, input_path=None) -> Dict[str, CleanedPost]:
        """Output wrapper

        - calls loop user locations method
        - optionally initializes output to file
        """
        if input_path is None:
            # load from ingested data
            cleaned_post_dict = self.process_cleaned_data()
        else:
            # load from file store
            cleaned_post_dict = self.load_cleaned_data(input_path)
        return cleaned_post_dict

    def load_cleaned_data(self, input_path):
        """Get cleaned Post Dict from intermediate
        data stored in file"""
        input_file = Path.cwd() / input_path
        if not input_file.exists():
            raise ValueError(f"File does not exist: {input_file}")
        cleaned_post_dict = self._loop_cleaned_data(input_file)
        return cleaned_post_dict

    def process_cleaned_data(self):
        """Get cleaned Post Dict from ingested data"""
        if self.write_cleaned_data:
            with open(self.output_folder / 'Output_cleaned.csv', 'w',
                      encoding='utf8') as csvfile:
                # get headerline from class structure
                headerline = ','.join(CleanedPost._fields)
                csvfile.write(f'{headerline}\n')
                # values will be written with CSV writer module
                datawriter = csv.writer(
                    csvfile, delimiter=',', lineterminator='\n',
                    quotechar='"', quoting=csv.QUOTE_NONNUMERIC)
                cleaned_post_dict = self._loop_loc_per_userid(
                    datawriter)
        else:
            cleaned_post_dict = self._loop_loc_per_userid(None)
        if self.topic_modeling:
            self._write_topic_models()
        return cleaned_post_dict

    def _get_item_stats(self) -> Dict['ClusterType', NamedTuple]:
        """After data is loaded, this collects data and stats
        for distribution of tags, emoji and locations

        - prepare data for tag maps clustering
        - store to self.data_prepared
        """
        if not self.cleaned_stats:
            self._init_item_stats()
        return self.cleaned_stats

    def _init_item_stats(self):
        """Init stats for selected cls_types"""
        for cls_type in self.cluster_types:
            self.cleaned_stats[cls_type] = self._prepare_item_stats(
                cls_type)

    def _prepare_item_stats(self, cls_type):
        """Calculate overall tag and emoji statistics

        - write results (optionally) to file
        """
        # init named tuple
        PreparedStats = namedtuple(
            'PreparedStats',
            'top_items_list total_unique_items total_item_count '
            'max_items')
        # top lists and unique
        item_stats = self._get_top_list(cls_type)
        top_items_list = item_stats.top_items
        total_unique_items = item_stats.total_unique
        itemcount_without_longtail = item_stats.total_without_longtail
        # top counts
        total_item_count = PrepareData._get_total_count(
            top_items_list, self.total_item_counter[cls_type])
        # assign stats to structure
        # update max_item from optionally long tail removal
        if itemcount_without_longtail and cls_type in [EMOJI, TAGS]:
            max_items = itemcount_without_longtail
        else:
            max_items = self.max_items
        item_stats = PreparedStats(
            top_items_list, total_unique_items, total_item_count,
            max_items)
        return item_stats

    def _update_toplists(self, lbsn_post):
        """Calculate toplists for emoji, tags and locations

        - adds tag/emojicount of this post to overall
          tag/emojicount for this user,
        - initialize counter for user if not already done
        """
        for cls_type in [EMOJI, TAGS, TOPICS]:
            if cls_type not in self.cluster_types:
                continue
            if cls_type in [TAGS, TOPICS]:
                # todo: TOPIC implementation
                item_list = lbsn_post.hashtags
            else:
                item_list = lbsn_post.emoji
            if not item_list:
                continue
            self.useritem_counts_global[cls_type][
                lbsn_post.user_guid].update(
                item_list)
            self.total_item_counter[cls_type].update(item_list)
        # locations
        if lbsn_post.loc_id:
            # update single item hack
            # there're more elegant ways to do this
            self.useritem_counts_global[LOCATIONS][
                lbsn_post.user_guid].update(
                (lbsn_post.loc_id,))
            self.total_item_counter[LOCATIONS].update((lbsn_post.loc_id,))

    @staticmethod
    def _write_toplist(self, top_list,
                       list_type, max_items, output_folder,
                       locid_name_dict=None):
        """Write toplists to file

        e.g.:
            tag, usercount
            toptag1, 1231
            toptag2, 560
            ...
        """
        if len(top_list) == 0:
            return

        # only ever write top 1000 to file
        max_to_write = min(1000, max_items)
        top_list = top_list[:max_to_write]
        if list_type == LOCATIONS and locid_name_dict:
            # get name for locid, if possible
            top_list = [(Utils._get_locname(
                item.name, locid_name_dict), item.ucount) for item in top_list]
        # construct string
        top_list_store = ''.join(
            "%s,%i" % v + '\n' for v in top_list)
        # overwrite, if exists:
        with open(output_folder / f'Output_top{list_type}.txt',
                  'w', encoding='utf8') as out_file:
            out_file.write(f'{list_type}, usercount\n')
            out_file.write(top_list_store)

    def write_toplists(self):
        """Writes toplists (tags, emoji, locations) to file"""
        for cls_type in self.cluster_types:
            top_list = self.cleaned_stats[cls_type].top_items_list
            max_items = self.cleaned_stats[cls_type].max_items
        PrepareData._write_toplist(
            top_list, cls_type, max_items,
            self.output_folder, self.locid_locname_dict)

    def _get_top_list(self, cls_type: ClusterType = TAGS) -> NamedTuple:
        """Get Top Tags on a per user basis, i.e.

        - the global number of distinct users who used each distinct tag
        - this ignores duplicate use of
        - calculation is based on dict userdict_tagcounters_global,
            with counters of tags for each user
        Returns:
            - list of top tags up to tmax [1000]
            - count of total unique tags
        """
        # create named tuple for result for easier referencing
        item_stats = namedtuple(
            'item_stats',
            'top_items total_unique total_without_longtail')
        # also create a named tuple for item counter object
        item_counter = collections.namedtuple(
            'item_counter', 'name ucount')
        overall_usercount_per_item = collections.Counter()
        for item_hash in self.useritem_counts_global[cls_type].values():
            # taghash contains unique values (= strings) for each user,
            # thus summing up these taghashes counts each user
            # only once per tag (or emoji)
            overall_usercount_per_item.update(item_hash)
        total_unique = len(overall_usercount_per_item)
        # get all items for "locations"
        # but clip list for tags and emoji
        if cls_type in (TAGS, EMOJI):
            max_items = self.max_items
        else:
            max_items = None
        top_items_list = overall_usercount_per_item.most_common(max_items)
        # convert list of item counts into list of namedtuple
        top_items_list = [
            item_counter(*ic_tuple) for ic_tuple in top_items_list]
        if self.remove_long_tail is True:
            total_without_longtail = self._remove_long_tail(
                top_items_list, cls_type)
        return item_stats(top_items_list, total_unique, total_without_longtail)

    @staticmethod
    def _get_total_count(top_list, top_counter):
        """Calculate Total Tags for selected

        Arguments:
        top_list (Long Tail Stat)
        top_counter (Reference to counter object)
        """
        total_count = 0
        for item in top_list:
            count = top_counter.get(item[0])
            if count:
                total_count += count
        return total_count

    def _remove_long_tail(self,
                          top_list: List[Tuple[str, int]],
                          listtype: ClusterType
                          ) -> int:
        """Removes all items from list that are used by less

        than x number of users,
        where x is given as input arg limit_bottom_user_count
            Note: since list is a mutable object, method
            will modify top_tags_list
        """
        if listtype == LOCATIONS:
            # keep all locations
            return len(top_list)
        elif listtype == EMOJI:
            # emoji use a smaller area than tags on the map
            # therefore we can keep more emoji
            # (e.g..: use 2 instead of 5)
            bottomuser_count = math.trunc(
                self.limit_bottom_user_count/2)
        else:
            bottomuser_count = self.limit_bottom_user_count
        indexMin = next((i for i, (t1, t2) in enumerate(
            top_list) if t2 < bottomuser_count
        ), None)
        if not indexMin:
            return
        len_before = len(top_list)
        # delete based on slicing
        del top_list[indexMin:]
        len_after = len(top_list)
        if len_before == len_after:
            # if no change, return
            return len_after
        self.log.info(
            f'Long tail removal: Filtered {len_before - len_after} '
            f'{listtype} that were used by less than '
            f'{bottomuser_count} users.')
        return len_after

    def _loop_loc_per_userid(self, datawriter=None):
        """Will produce final cleaned list
        of items to be processed by clustering.

        - optionally writes entries to file, if handler exists
        """
        cleaned_post_dict = defaultdict(CleanedPost)
        for user_key, locationhash in \
                self.locations_per_userid_dict.items():
            for location in locationhash:
                locid_userid = f'{location}::{user_key}'
                post_latlng = location.split(':')

                first_post = self.userlocations_firstpost_dict.get(
                    locid_userid, None)
                if first_post is None:
                    return
                # create tuple with cleaned photo data
                cleaned_post = self._compile_cleaned_post(
                    first_post, locid_userid, post_latlng, user_key)
                if datawriter is not None:
                    PrepareData._write_location_tocsv(
                        datawriter, cleaned_post)
                if self.topic_modeling:
                    self._update_topic_models(
                        cleaned_post, user_key)
                cleaned_post_dict[cleaned_post.guid] = \
                    cleaned_post
                # update boundary
                self.bounds._upd_latlng_bounds(
                    cleaned_post.lat, cleaned_post.lng)
        return cleaned_post_dict

    def _loop_cleaned_data(self, cdata: Path):
        """Create cleaned post dict from intermediate data file store"""
        cleaned_post_dict = defaultdict(CleanedPost)
        with open(cdata, 'r', newline='', encoding='utf8') as f:
            cpost_reader = csv.DictReader(
                f,
                delimiter=',',
                quotechar='"',
                quoting=QUOTE_MINIMAL)
            for cpost in cpost_reader:
                # row_num += 1
                self.count_glob += 1
                cleaned_post = PrepareData._parse_cleaned_post(cpost)
                cleaned_post_dict[cleaned_post.guid] = \
                    cleaned_post
                # update statistics from cleaned post
                self.add_record(cleaned_post)
                # update boundary
                self.bounds._upd_latlng_bounds(
                    cleaned_post.lat, cleaned_post.lng)
        return cleaned_post_dict

    def _write_topic_models(self):
        """Initialize two lists for topic modeling output

        - hashed (anonymized) output (*add salt)
        - original output
        """
        headerline = "topics,post_ids,user_ids\n"
        with open(
            self.output_folder / 'Output_usertopics_anonymized.csv',
                'w', encoding='utf8') as csvfile_anon, open(
                    self.output_folder / 'Output_usertopics.csv',
                    'w', encoding='utf8') as csvfile:
            dw_list = list()
            for cfile in (csvfile, csvfile_anon):
                cfile.write(headerline)
                dw = csv.writer(cfile, delimiter=',',
                                lineterminator='\n', quotechar='"',
                                quoting=csv.QUOTE_NONNUMERIC)
                dw_list.append(dw)
            self._write_topic_rows(dw_list)

    def _write_topic_rows(self, dw_list):
        """Write Topic models to file"""
        dw = dw_list[0]
        dw_anon = dw_list[1]

        def _join_encode(keys):
            joined_keys = ",".join(keys)
            joined_encoded_keys = ",".join(
                [Utils.encode_string(post_id) for post_id in keys])
            return joined_keys, joined_encoded_keys
        for user_key, topics in self.user_topiclist_dict.items():
            joined_topics = " ".join(topics)
            post_keys = self.user_post_ids_dict.get(user_key, None)
            joined_keys, joined_encoded_keys = _join_encode(post_keys)
            dw_anon.writerow([joined_topics,
                              "{" + joined_encoded_keys + "}",
                              Utils.encode_string(user_key)])
            dw.writerow([joined_topics,
                         "{" + joined_keys + "}",
                         str(user_key)])

    def _update_topic_models(self,
                             cleaned_post_location,
                             user_key):
        """If Topic Modeling enabled, update
        required dictionaries with merged words from
        title, tags and post_body
        """
        if not len(
                cleaned_post_location.hashtags) == 0:
            self.user_topiclist_dict[user_key] |= \
                cleaned_post_location.hashtags
            # also use descriptions for Topic Modeling
            self. user_topiclist_dict[user_key] |= \
                cleaned_post_location.post_body
            # Bit wise or and assignment in one step.
            # -> assign PhotoGuid to UserDict list
            # if not already contained
            self.user_post_ids_dict[user_key] |= {
                cleaned_post_location.guid}
            # UserPhotoFirstThumb_dict[user_key] = photo[5]

    @staticmethod
    def _parse_cleaned_post(cpost: Dict[str, str]) -> CleanedPost:
        """Process single cleaned post from (file) dict stream"""
        cleaned_post = CleanedPost(
            origin_id=cpost.get("origin_id"),
            lat=float(cpost.get("lat")),
            lng=float(cpost.get("lng")),
            guid=cpost.get("post_guid"),
            user_guid=cpost.get("user_id"),
            post_body=set(cpost.get("post_body")),
            post_create_date=cpost.get("post_create_date"),
            post_publish_date=cpost.get("post_publish_date"),
            post_views_count=int(cpost.get("post_views_count")),
            post_like_count=int(cpost.get("post_like_count")),
            emoji=set(cpost.get("emoji").split(';')),
            hashtags=set(cpost.get("hashtags").split(';')),
            loc_id=cpost.get("loc_id"),
            loc_name=cpost.get("loc_name")
        )
        return cleaned_post

    def _compile_cleaned_post(self, first_post, locid_userid,
                              post_latlng, user_key) -> CleanedPost:
        """Merge cleaned post from all posts of a certain user
        at a specific location. This is producing the final CleanedPost.

        - some information is not needed, those post attributes
        are simply skipped (e.g. location name)
        - some information must not be merged, this can be directly copied
        from the first post at a location/user (e.g. origin_id - will always be
        the same for a particular user, post_create_date, post_publish_date)
        - some information (e.g. hashtags) need merge with removing dupliates:
        use prepared dictionaries
        - some important information is type-checked (longitude, latitude)

        Keyword arguments:
        first_post      -- first post of a user_guid at a location
        locid_userid    -- user_guid and loc_id in merged format
                           (f'{location}::{user_key}')
        post_latlng     -- tuple with lat/lng coordinates
        user_key        -- user_guid

        Note:
            ("",) means: substitute empty tuple as default
        """

        merged_wordlist = PrepareData._get_merged(
            self.userlocation_wordlist_dict, locid_userid)
        merged_emojilist = PrepareData._get_merged(
            self.userlocation_emojilist_dict, locid_userid)
        merged_taglist = PrepareData._get_merged(
            self.userlocation_taglist_dict, locid_userid)
        cleaned_post = CleanedPost(
            origin_id=first_post.origin_id,
            lat=float(post_latlng[0]),
            lng=float(post_latlng[1]),
            guid=first_post.guid,
            user_guid=user_key,
            post_body=merged_wordlist,
            post_create_date=first_post.post_create_date,
            post_publish_date=first_post.post_publish_date,
            post_views_count=first_post.post_views_count,
            post_like_count=first_post.post_like_count,
            emoji=merged_emojilist,
            hashtags=merged_taglist,
            loc_id=first_post.loc_id,
            loc_name=first_post.loc_name
        )
        return cleaned_post

    @staticmethod
    def _get_merged(ref_dict: Dict, locid_userid: str) -> Set[str]:
        """Gets set of words for userlocid from ref dictionary

        Note: since using defaultdict,
        keys not found will return empty set()
        """
        value = ref_dict[locid_userid]
        return value

    @staticmethod
    def _write_location_tocsv(datawriter: TextIO,
                              cleaned_post_location: CleanedPost) -> None:
        """Writes a single record of cleaned posts to CSV list

        - write intermediate cleaned post data to file for later use
        Arguments
        datawriter              -      open file file_handle to
                                       output file
        cleaned_post_location   -      cleaned post of type CleanedPost
                                       (namedtuple)
        """
        ploc_list = PrepareData._cleaned_ploc_tolist(
            cleaned_post_location)
        datawriter.writerow(ploc_list)

    @staticmethod
    def _cleaned_ploc_tolist(cleaned_post_location: CleanedPost
                             ) -> List[str]:
        """Converts a cleaned post structure to list for CSV write"""
        attr_list = list()
        for attr in cleaned_post_location:
            if isinstance(attr, set):
                attr_list.append(";".join(attr))
            else:
                attr_list.append(attr)
        return attr_list

    def _get_cleaned_wordlist(self, post_body_string):
        cleaned_post_body = Utils._remove_special_chars(post_body_string)
        cleaned_wordlist = PrepareData._get_wordlist(cleaned_post_body)
        return cleaned_wordlist

    @staticmethod
    def _get_wordlist(cleaned_post_body):
        """split by space-characterm, filter by length"""
        wordlist = [word for word in cleaned_post_body.lower().split(
            ' ') if len(word) > 2]
        return wordlist

    def global_stats_report(self, cleaned=None):
        """Report global stats after data has been read"""
        if cleaned is None:
            cleaned = True
        self.log.info(
            f'Total user count (UC): '
            f'{len(self.locations_per_userid_dict)}')
        self.log.info(
            f'Total user post locations (UPL): '
            f'{len(self.distinct_userlocations_set)}')
        if not cleaned:
            return
        if not self.cleaned_stats:
            self._init_item_stats()
        self.log.info(
            f'Total (cleaned) post count (PC): '
            f'{self.count_glob:02d}')
        self.log.info(
            f'Total (cleaned) tag count (PTC): '
            f'{self.cleaned_stats[TAGS].total_item_count}')
        self.log.info(
            f'Total (cleaned) emoji count (PEC): '
            f'{self.cleaned_stats[EMOJI].total_item_count}')
