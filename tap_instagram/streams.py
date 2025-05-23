"""Stream type classes for tap-instagram."""

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pendulum
import requests
from singer_sdk import typing as th  # JSON Schema typing helpers
from singer_sdk.helpers.jsonpath import extract_jsonpath

from tap_instagram.client import InstagramStream


# SCHEMAS_DIR = Path(__file__).parent / Path("./schemas")


class UsersStream(InstagramStream):
    """Define custom stream."""

    name = "users"
    path = "/{user_id}"
    primary_keys = ["id", "date"]
    replication_key = None
    fields = [
        "id",
        "ig_id",
        "name",
        "website",
        "username",
        "biography",
        "followers_count",
        "follows_count",
        "media_count",
    ]
    # Optionally, you may also use `schema_filepath` in place of `schema`:
    # schema_filepath = SCHEMAS_DIR / "users.json"
    schema = th.PropertiesList(
        th.Property("id", th.StringType),
        th.Property("date", th.DateType),
        th.Property("ig_id", th.IntegerType),
        th.Property("name", th.StringType),
        th.Property("website", th.StringType),
        th.Property("username", th.StringType),
        th.Property("biography", th.StringType),
        th.Property("followers_count", th.IntegerType),
        th.Property("follows_count", th.IntegerType),
        th.Property("media_count", th.IntegerType),
    ).to_dict()

    @property
    def partitions(self) -> Optional[List[dict]]:
        return [{"user_id": user_id} for user_id in self.config["ig_user_ids"]]

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        params["fields"] = ",".join(self.fields)
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        return {"user_id": record["id"]}

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        for row in extract_jsonpath(self.records_jsonpath, input=response.json()):
            row["date"] = pendulum.now("UTC").format(
                    "YYYY-MM-DD"
            )
            yield row


class MediaStream(InstagramStream):
    """Define custom stream."""

    name = "media"
    path = "/{user_id}/media"  # user_id is populated using child context keys from UsersStream
    parent_stream_type = UsersStream
    primary_keys = ["id"]
    replication_key = "timestamp"
    records_jsonpath = "$.data[*]"
    fields = [
        "id",
        "ig_id",
        "caption",
        "comments_count",
        "is_comment_enabled",
        "like_count",
        "media_product_type",
        "media_type",
        "media_url",
        "owner",
        "permalink",
        "shortcode",
        "thumbnail_url",
        "timestamp",
        "username",
    ]
    # Optionally, you may also use `schema_filepath` in place of `schema`:
    # schema_filepath = SCHEMAS_DIR / "users.json"
    schema = th.PropertiesList(
        th.Property(
            "id",
            th.StringType,
            description="Media ID.",
        ),
        th.Property(
            "ig_id",
            th.StringType,
            description="Instagram media ID.",
        ),
        th.Property(
            "user_id",
            th.StringType,
            description="Instagram user ID.",
        ),
        th.Property(
            "caption",
            th.StringType,
            description="Caption. Excludes album children. @ symbol excluded unless the app user can perform "
                        "admin-equivalent tasks on the Facebook Page connected to the Instagram account used to "
                        "create the caption.",
        ),
        th.Property(
            "comments_count",
            th.IntegerType,
            description="Count of comments on the media. Excludes comments on album child media and the media's "
                        "caption. Includes replies on comments.",
        ),
        th.Property(
            "is_comment_enabled",
            th.BooleanType,
            description="Indicates if comments are enabled or disabled. Excludes album children.",
        ),
        th.Property(
            "like_count",
            th.IntegerType,
            description="Count of likes on the media. Excludes likes on album child media and likes on promoted posts "
                        "created from the media. Includes replies on comments.",
        ),
        th.Property(
            "media_product_type",
            th.StringType,
            description="Surface where the media is published. Can be AD, FEED, IGTV, or STORY.",
        ),
        th.Property(
            "media_type",
            th.StringType,
            description="Media type. Can be CAROUSEL_ALBUM, IMAGE, or VIDEO.",
        ),
        th.Property(
            "media_url",
            th.StringType,
            description="Media URL. Will be omitted from responses if the media contains copyrighted material, "
                        "or has been flagged for a copyright violation.",
        ),
        th.Property(
            "owner",
            th.ObjectType(
                th.Property(
                    "id",
                    th.StringType,
                    description="ID of Instagram user who created the media.",
                ),
                th.Property(
                    "username",
                    th.StringType,
                    description="Username of Instagram user who created the media.",
                ),
            ),
            description="ID of Instagram user who created the media. Only returned if the app user making the query "
                        "also created the media, otherwise username field will be returned instead.",
        ),
        th.Property(
            "permalink",
            th.StringType,
            description="Permanent URL to the media.",
        ),
        th.Property(
            "shortcode",
            th.StringType,
            description="Shortcode to the media.",
        ),
        th.Property(
            "thumbnail_url",
            th.StringType,
            description="Media thumbnail URL. Only available on VIDEO media.",
        ),
        th.Property(
            "timestamp",
            th.DateTimeType,
            description="ISO 8601 formatted creation date in UTC (default is UTC ±00:00)",
        ),
        th.Property(
            "username",
            th.StringType,
            description="Username of user who created the media.",
        ),
    ).to_dict()

    def make_since_param(self, context: Optional[dict]) -> datetime:
        state_ts = self.get_starting_timestamp(context)
        if state_ts:
            return pendulum.instance(state_ts).subtract(
                days=self.config["media_insights_lookback_days"]
            )
        else:
            return state_ts

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        params["fields"] = ",".join(self.fields)
        params["since"] = self.make_since_param(context)
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        return {
            "user_id": context["user_id"],
            "media_id": record["id"],
            "media_type": record["media_type"],
            # media_product_type not present for carousel children media
            "media_product_type": record.get("media_product_type"),
        }

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        for row in extract_jsonpath(self.records_jsonpath, input=response.json()):
            if "timestamp" in row:
                row["timestamp"] = pendulum.parse(row["timestamp"]).format(
                    "YYYY-MM-DD HH:mm:ss"
                )
            yield row


class StoriesStream(InstagramStream):
    """Define custom stream."""

    name = "stories"
    path = "/{user_id}/stories"  # user_id is populated using child context keys from UsersStream
    parent_stream_type = UsersStream
    primary_keys = ["id"]
    records_jsonpath = "$.data[*]"
    fields = [
        "id",
        "ig_id",
        "caption",
        "comments_count",
        "like_count",
        "media_product_type",
        "media_type",
        "media_url",
        "owner",
        "permalink",
        "shortcode",
        "thumbnail_url",
        "timestamp",
        "username",
    ]
    # Optionally, you may also use `schema_filepath` in place of `schema`:
    # schema_filepath = SCHEMAS_DIR / "users.json"
    schema = th.PropertiesList(
        th.Property(
            "id",
            th.StringType,
            description="Media ID.",
        ),
        th.Property(
            "ig_id",
            th.StringType,
            description="Instagram media ID.",
        ),
        th.Property(
            "user_id",
            th.StringType,
            description="Instagram user ID.",
        ),
        th.Property(
            "caption",
            th.StringType,
            description="Caption. Excludes album children. @ symbol excluded unless the app user can perform "
                        "admin-equivalent tasks on the Facebook Page connected to the Instagram account used to "
                        "create the caption.",
        ),
        th.Property(
            "comments_count",
            th.IntegerType,
            description="Count of comments on the media. Excludes comments on album child media and the media's "
                        "caption. Includes replies on comments.",
        ),
        th.Property(
            "is_comment_enabled",
            th.BooleanType,
            description="Indicates if comments are enabled or disabled. Excludes album children.",
        ),
        th.Property(
            "like_count",
            th.IntegerType,
            description="Count of likes on the media. Excludes likes on album child media and likes on promoted posts "
                        "created from the media. Includes replies on comments.",
        ),
        th.Property(
            "media_product_type",
            th.StringType,
            description="Surface where the media is published. Can be AD, FEED, IGTV, or STORY.",
        ),
        th.Property(
            "media_type",
            th.StringType,
            description="Media type. Can be CAROUSEL_ALBUM, IMAGE, or VIDEO.",
        ),
        th.Property(
            "media_url",
            th.StringType,
            description="Media URL. Will be omitted from responses if the media contains copyrighted material, "
                        "or has been flagged for a copyright violation.",
        ),
        th.Property(
            "owner",
            th.ObjectType(
                th.Property(
                    "id",
                    th.StringType,
                    description="ID of Instagram user who created the media.",
                ),
                th.Property(
                    "username",
                    th.StringType,
                    description="Username of Instagram user who created the media.",
                ),
            ),
            description="ID of Instagram user who created the media. Only returned if the app user making the query "
                        "also created the media, otherwise username field will be returned instead.",
        ),
        th.Property(
            "permalink",
            th.StringType,
            description="Permanent URL to the media.",
        ),
        th.Property(
            "shortcode",
            th.StringType,
            description="Shortcode to the media.",
        ),
        th.Property(
            "thumbnail_url",
            th.StringType,
            description="Media thumbnail URL. Only available on VIDEO media.",
        ),
        th.Property(
            "timestamp",
            th.DateTimeType,
            description="ISO 8601 formatted creation date in UTC (default is UTC ±00:00)",
        ),
        th.Property(
            "username",
            th.StringType,
            description="Username of user who created the media.",
        ),
    ).to_dict()

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        params["fields"] = ",".join(self.fields)
        return params

    def get_child_context(self, record: dict, context: Optional[dict]) -> dict:
        return {
            "user_id": context["user_id"],
            "media_id": record["id"],
            "media_type": record["media_type"],
            # media_product_type not present for carousel children media
            "media_product_type": record.get("media_product_type"),
        }

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        for row in extract_jsonpath(self.records_jsonpath, input=response.json()):
            if "timestamp" in row:
                row["timestamp"] = pendulum.parse(row["timestamp"]).format(
                    "YYYY-MM-DD HH:mm:ss"
                )
            yield row


class MediaChildrenStream(MediaStream):
    """Define custom stream."""

    name = "media_children"
    parent_stream_type = MediaStream
    state_partitioning_keys = ["user_id"]
    path = "/{media_id}/children"  # media_id is populated using child context keys from MediaStream
    # caption, comments_count, is_comment_enabled, like_count, media_product_type
    # not available on album children
    # TODO: Is media_product_type available on children of some media types? carousel vs album children?
    # https://developers.facebook.com/docs/instagram-api/reference/ig-media#fields
    fields = [
        "id",
        "ig_id",
        "media_type",
        "media_url",
        "owner",
        "permalink",
        "shortcode",
        "thumbnail_url",
        "timestamp",
        "username",
    ]

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        for row in extract_jsonpath(self.records_jsonpath, input=response.json()):
            if "timestamp" in row:
                row["timestamp"] = pendulum.parse(row["timestamp"]).format(
                    "YYYY-MM-DD HH:mm:ss"
                )
            yield row


class MediaInsightsStream(InstagramStream):
    """Define custom stream."""

    name = "media_insights"
    path = "/{media_id}/insights"
    parent_stream_type = MediaStream
    state_partitioning_keys = ["user_id"]
    primary_keys = ["id", "name", "date"]
    replication_key = "end_time"
    records_jsonpath = "$.data[*]"

    schema = th.PropertiesList(
        th.Property(
            "id",
            th.StringType,
            description="",
        ),
        th.Property(
            "name",
            th.StringType,
            description="",
        ),
        th.Property(
            "date",
            th.DateType,
            description="",
        ),
        th.Property(
            "end_time",
            th.DateTimeType,
            description="",
        ),
        th.Property(
            "value",
            th.IntegerType,
            description="",
        )
    ).to_dict()

    @staticmethod
    def _metrics_for_media_type(media_type: str, media_product_type: str):
        # TODO: Define types for these function args
        if media_product_type == 'FEED' and media_type in ['VIDEO', 'IMAGE']:
            return ['total_interactions',
                                  # 'engagement', DEPRECATED
                                  #'impressions',
                                  'reach',
                                  'saved',
                                 # 'video_views',
                                  'follows',
                                  'profile_visits']

        elif media_type == 'CAROUSEL_ALBUM':
            return ['total_interactions',
                                      #'impressions',
                                      'reach',
                                      'saved',
                                      #'video_views'
                   ]

        elif media_product_type == 'REELS':
            return ['comments',
                                  'likes',
                                  'plays',
                                  'reach',
                                  'saved',
                                  'shares',
                                  'total_interactions']

        elif media_product_type == 'STORY':
            return [
                # "exits",
               # "impressions",
                "reach",
                "replies",
                # "taps_forward",
                # "taps_back",
            ]
        else:
            raise ValueError(
                f"media_type from parent record must be one of IMAGE, VIDEO, CAROUSEL_ALBUM, got: {media_type}"
            )

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        metrics = self._metrics_for_media_type(
            context["media_type"], context["media_product_type"]
        )
        params["metric"] = ",".join(metrics)
        return params

    def validate_response(self, response: requests.Response) -> None:
        if response.json().get("error", {}).get(
                "error_user_title"
        ) == "Media posted before business account conversion" or "(#10) Not enough viewers for the media to show insights" in str(
            response.json().get("error", {}).get("message")
        ):
            self.logger.warning(f"Skipping: {response.json()['error']}")
            return
        super().validate_response(response)

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        resp_json = response.json()
        # Handle the specific case where FB returns error because media was posted before business acct creation
        # TODO: Refactor to raise a specific error in validate_response and handle that instead
        if response.json() is None:
            resp_json = {
                "error": response.text
            }
            self.logger.warning(f"Skipping: {response.text}")
            return
        if resp_json.get("error", {}).get(
                "error_user_title"
        ) == "Media posted before business account conversion" or "(#10) Not enough viewers for the media to show insights" in str(
            resp_json.get("error", {}).get("message")
        ) or resp_json.get("data") is None:
            self.logger.warning(f"Skipping: {response.text}")
            return

        for row in resp_json["data"]:
            base_item = {
                "name": row["name"],
                "id": row["id"].split("/")[0]
            }

            if "values" in row:
                for values in row["values"]:
                    item = {
                        "value": values["value"],
                        "date": pendulum.now("UTC").format(
                            "YYYY-MM-DD"
                        ),
                        "end_time": pendulum.now("UTC").format(
                            "YYYY-MM-DD HH:mm:ss"
                        ),
                    }
                    item.update(base_item)
                    yield item


# class MediaInsightsStream(MediaInsightsStream):
# """Define custom stream."""

#    name = "media_insights"
#    parent_stream_type = MediaStream
#   state_partitioning_keys = ["user_id"]


# Insights not available for children media objects
# https://developers.facebook.com/docs/instagram-api/reference/ig-media/insights#limitations
# class MediaChildrenInsightsStream(BaseMediaInsightsStream):
#     """Define custom stream."""
#     name = "media_children_insights"
#     parent_stream_type = MediaChildrenStream


class StoryInsightsStream(InstagramStream):
    """Define custom stream."""

    name = "story_insights"
    path = "/{media_id}/insights"
    parent_stream_type = StoriesStream
    state_partitioning_keys = ["user_id"]
    primary_keys = ["id", "name", "date"]
    replication_key = "end_time"
    records_jsonpath = "$.data[*]"

    schema = th.PropertiesList(
        th.Property(
            "id",
            th.StringType,
            description="",
        ),
        th.Property(
            "name",
            th.StringType,
            description="",
        ),
        th.Property(
            "date",
            th.DateType,
            description="",
        ),
        th.Property(
            "end_time",
            th.DateTimeType,
            description="",
        ),
        th.Property(
            "value",
            th.IntegerType,
            description="",
        )
    ).to_dict()

    @staticmethod
    def _metrics_for_media_type(media_type: str, media_product_type: str):
        # TODO: Define types for these function args
        if media_type in ("IMAGE", "VIDEO"):
            if media_product_type == "STORY":
                return [
                    # "exits",
                    #"impressions",
                    "reach",
                    "replies",
                    # "taps_forward",
                    # "taps_back",
                ]
            else:  # media_product_type is "AD" or "FEED"
                metrics = [
                    #'impressions',
                    'reach',
                    'saved',
                    'video_views',
                    'follows',
                    'comments',
                    'likes',
                    'shares',
                    'profile_visits',
                    'total_interactions'
                ]
                if media_type == "VIDEO":
                    metrics.append("video_views")
                return metrics
        elif media_type == "CAROUSEL_ALBUM":
            return [
                "total_interactions",
                #"impressions",
                "reach",
                "saved",
                "video_views",
            ]
        elif media_type == "REELS":
            return ['comments',
                    'likes',
                    'plays',
                    'reach',
                    'saved',
                    'shares',
                    'total_interactions']

        else:
            raise ValueError(
                f"media_type from parent record must be one of IMAGE, VIDEO, CAROUSEL_ALBUM, got: {media_type}"
            )

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        params = super().get_url_params(context, next_page_token)
        metrics = self._metrics_for_media_type(
            context["media_type"], context["media_product_type"]
        )
        params["metric"] = ",".join(metrics)
        return params

    def validate_response(self, response: requests.Response) -> None:
        if response.json() is None:
            resp_json = {
                "error": response.text
            }
            self.logger.warning(f"Skipping: {response.text}")
            return
        if response.json().get("error", {}).get(
                "error_user_title"
        ) == "Media posted before business account conversion" or "(#10) Not enough viewers for the media to show insights" in str(
            response.json().get("error", {}).get("message")
        ) or response.json().get("data") is None:
            self.logger.warning(f"Skipping: {response.text}")
            return
        super().validate_response(response)

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        resp_json = response.json()
        # Handle the specific case where FB returns error because media was posted before business acct creation
        # TODO: Refactor to raise a specific error in validate_response and handle that instead
        if resp_json.get("error", {}).get(
                "error_user_title"
        ) == "Media posted before business account conversion" or "(#10) Not enough viewers for the media to show insights" in str(
            resp_json.get("error", {}).get("message")
        ):
            return

        for row in resp_json["data"]:
            base_item = {
                "name": row["name"],
                "id": row["id"].split("/")[0]
            }

            if "values" in row:
                for values in row["values"]:
                    item = {
                        "value": values["value"],
                        "date": pendulum.now("UTC").format(
                            "YYYY-MM-DD"
                        ),
                        "end_time": pendulum.now("UTC").format(
                            "YYYY-MM-DD HH:mm:ss"
                        ),
                    }
                    item.update(base_item)
                    yield item


class UserInsightsStream(InstagramStream):
    parent_stream_type = UsersStream
    path = "/{user_id}/insights"  # user_id is populated using child context keys from UsersStream
    primary_keys = ["id", "name", "date"]
    replication_key = "end_time"
    records_jsonpath = "$.data[*]"
    has_pagination = True
    min_start_date: datetime = pendulum.now("UTC").subtract(days=29)
    max_end_date: datetime = pendulum.today("UTC").subtract(days=1)
    max_time_window: timedelta = pendulum.duration(days=30)
    time_period = "day"  # TODO: Use an Enum type instead
    metrics: List[str]

    # Optionally, you may also use `schema_filepath` in place of `schema`:
    # schema_filepath = SCHEMAS_DIR / "users.json"
    schema = th.PropertiesList(
        th.Property(
            "id",
            th.StringType,
            description="",
        ),
        th.Property(
            "name",
            th.StringType,
            description="",
        ),
        th.Property(
            "date",
            th.DateType,
            description="",
        ),
        th.Property(
            "end_time",
            th.DateTimeType,
            description="",
        ),
        th.Property(
            "value",
            th.IntegerType,
            description="",
        )
    ).to_dict()

    def _fetch_time_based_pagination_range(
            self,
            context,
            min_since: datetime,
            max_until: datetime,
            max_time_window: timedelta,
    ) -> Tuple[datetime, datetime]:
        """
        Make "since" and "until" pagination timestamps
        Args:
            context:
            min_since: Min datetime for "since" parameter. Defaults to 2 years ago, max historical data
                       supported for Facebook metrics.
            max_until: Max datetime for which data is available. Defaults to a day ago.
            max_time_window: Maximum duration (as a "timedelta") between "since" and "until". Default to
                             30 days, max window supported by Facebook

        Returns: DateTime objects for "since" and "until"
        """
        try:
            since = min(self.get_starting_timestamp(context), min_since)
            window_end = pendulum.instance(since).add(seconds=max_time_window.seconds)
        # seeing cases where self.get_starting_timestamp() is null
        # possibly related to target-bigquery pushing malformed state - https://gitlab.com/meltano/sdk/-/issues/300
        except TypeError as e:
            self.logger.critical(e)
            since = min_since
            window_end = pendulum.instance(since).add(days=1)
        until = max(window_end, max_until)
        return since, until

    def get_url_params(
            self, context: Optional[dict], next_page_token: Optional[Any]
    ) -> Dict[str, Any]:
        # TODO: Is there a cleaner way to do this?
        params = super().get_url_params(context, next_page_token)
        if next_page_token:
            return params
        params["metric"] = ",".join(self.metrics)
        params["period"] = self.time_period

        if self.has_pagination:
            since, until = self._fetch_time_based_pagination_range(
                context,
                min_since=self.min_start_date,
                max_until=self.max_end_date,
                max_time_window=self.max_time_window,
            )
            params["since"] = since
            params["until"] = until
        return params

    def parse_response(self, response: requests.Response) -> Iterable[dict]:
        resp_json = response.json()

        # Handle the specific case where FB returns error responses
        # Check for various error conditions and log them appropriately
        if resp_json.get("error"):
            error_msg = resp_json.get("error", {}).get("message", "Unknown error")
            self.logger.warning(f"Skipping user insights due to API error: {error_msg}")
            return

        # Check if data field is missing or None
        if not resp_json.get("data"):
            self.logger.warning(f"Skipping user insights: No data returned from API")
            return

        for row in resp_json["data"]:
            base_item = {
                "name": row["name"],
                "id": row["id"].split("/")[0]
            }

            if "values" in row:
                for values in row["values"]:
                    # Special handling for online_followers which returns hourly JSON data
                    if row["name"] == "online_followers" and isinstance(values["value"], dict):
                        # Convert hourly data to peak online followers for the day
                        # online_followers shows how many followers were online each hour
                        # Taking the max gives us the peak online followers for that day
                        try:
                            hourly_values = [int(v) for v in values["value"].values() if str(v).isdigit()]
                            if hourly_values:
                                peak_value = max(hourly_values)
                            else:
                                peak_value = 0
                            item = {
                                "value": peak_value,
                                "date": pendulum.parse(values["end_time"]).format(
                                    "YYYY-MM-DD"
                                ),
                                "end_time": pendulum.parse(values["end_time"]).format(
                                    "YYYY-MM-DD HH:mm:ss"
                                ),
                            }
                            item.update(base_item)
                            yield item
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Could not parse online_followers hourly data: {e}")
                            continue
                    else:
                        # Normal handling for other metrics
                        item = {
                            "value": values["value"],
                            "date": pendulum.parse(values["end_time"]).format(
                                "YYYY-MM-DD"
                            ),
                            "end_time": pendulum.parse(values["end_time"]).format(
                                "YYYY-MM-DD HH:mm:ss"
                            ),
                        }
                        item.update(base_item)
                        yield item


class UserInsightsOnlineFollowersStream(UserInsightsStream):
    """Define custom stream."""

    name = "user_insights_online_followers"
    metrics = [
        "online_followers",
    ]
    time_period = "lifetime"


class UserInsightsFollowersStream(UserInsightsStream):
    """Define custom stream."""

    name = "user_insights_followers"
    metrics = [
        "follower_count",
    ]
    time_period = "day"


class UserInsightsDailyStream(UserInsightsStream):
    """Define custom stream."""

    name = "user_insights_daily"
    metrics = [
       # "email_contacts",
        #"get_directions_clicks",
       # "impressions",
        #"phone_call_clicks",
       # "profile_views",
        "reach",
        #"text_message_clicks",
        #"website_clicks",
    ]
    time_period = "day"


class UserInsightsWeeklyStream(UserInsightsStream):
    """Define custom stream."""

    name = "instagram_account_stat"
    metrics = [
        'follower_count',
        #'profile_views',
        #'impressions',
        'reach', #'email_contacts', 'get_directions_clicks',
        #'text_message_clicks', 'phone_call_clicks', 'website_clicks'
    ]
    time_period = "day"


class UserInsights28DayStream(UserInsightsStream):
    """Define custom stream."""

    name = "instagram_account_stat_"
    metrics = [
        #"impressions",
        "reach",
    ]
    time_period = "days_28"
