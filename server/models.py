#!/usr/bin/env python

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import PrimaryKeyConstraint
from sqlalchemy import String
from sqlalchemy import event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref
from sqlalchemy.orm import composite
from sqlalchemy.orm import relationship

from caching import cache
from settings import BASE_URL_VIDEOS
from settings import DB_URI
from video_repr import VideoRepresentation

Base = declarative_base()


# A marker for all models declared in this app
class CsMixin(object):
    pass


class Video(Base, CsMixin):
    __tablename__ = 'cs_videos'

    video_id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)

    type = Column(Enum('VOD', 'LIVE', name='cs_video_types'), nullable=False, default='LIVE')
    status = Column(Enum('EMPTY', 'UPLOADING', 'OK', 'ERROR'), nullable=False, default='EMPTY')

    # the count is only available after all segments are uploaded
    segment_count = Column(Integer, nullable=False, default=-1)
    segment_duration = Column(Integer, nullable=False, default=3000)

    # if a representation is not available, set its properties to null
    repr_1_name = Column(String(255), nullable=True)
    repr_1_bandwidth = Column(Integer, nullable=True)
    repr_1_width = Column(Integer, nullable=True)
    repr_1_height = Column(Integer, nullable=True)
    repr_1 = composite(VideoRepresentation, repr_1_name, repr_1_bandwidth, repr_1_width, repr_1_height)

    repr_2_name = Column(String(255), nullable=True)
    repr_2_bandwidth = Column(Integer, nullable=True)
    repr_2_width = Column(Integer, nullable=True)
    repr_2_height = Column(Integer, nullable=True)
    repr_2 = composite(VideoRepresentation, repr_2_name, repr_2_bandwidth, repr_2_width, repr_2_height)

    repr_3_name = Column(String(255), nullable=True)
    repr_3_bandwidth = Column(Integer, nullable=True)
    repr_3_width = Column(Integer, nullable=True)
    repr_3_height = Column(Integer, nullable=True)
    repr_3 = composite(VideoRepresentation, repr_3_name, repr_3_bandwidth, repr_3_width, repr_3_height)

    # each uri can be a dynamic resource (live streaming) or a static file (on demand)
    uri_mpd = Column(String(255), nullable=True)
    uri_m3u8 = Column(String(255), nullable=True)

    # thumbnail
    uri_thumbnail = Column(String(255), nullable=True)

    @hybrid_property
    def base_url(self):
        # this not saved into the database, but the client needs this
        return "%s/%s" % (BASE_URL_VIDEOS, self.video_id)


class VideoSegment(Base, CsMixin):
    __tablename__ = 'cs_segments'

    video_id = Column(Integer, ForeignKey(Video.video_id), index=True)
    segment_id = Column(Integer, autoincrement=False)

    # file location for uploaded file
    original_path = Column(String(255), nullable=True)
    original_extension = Column(String(50), nullable=False)

    # overall status
    status = Column(Enum('OK', 'ERROR', 'PROCESSING', 'NIL'), nullable=False, default='NIL')
    duration = Column(Integer, nullable=False, default=0)

    # segment status for each representation
    repr_1_status = Column(Enum('OK', 'ERROR', 'PROCESSING', 'NIL'), nullable=False, default='NIL')
    repr_2_status = Column(Enum('OK', 'ERROR', 'PROCESSING', 'NIL'), nullable=False, default='NIL')
    repr_3_status = Column(Enum('OK', 'ERROR', 'PROCESSING', 'NIL'), nullable=False, default='NIL')

    # media name for each type of playlist
    media_mpd = Column(String(255), nullable=True)
    media_m3u8 = Column(String(255), nullable=True)

    # relationship
    video = relationship(Video, backref=backref("segments", cascade="all, delete-orphan"))

    __table_args__ = (PrimaryKeyConstraint(video_id, segment_id, name='cs_segments_pk'), {},)


# For caching of the video list. The cache will be refresh whenever there is any change to the data.
# This is mostly to reduce the impact of polling (from the Admin UI) on the database.
# This also means that this server needs more work before it can be clustered.
class VideoListCache(object):
    @classmethod
    def clear(cls):
        cache.delete("cs2015_team03_all_videos")
        cache.delete("cs2015_team03_all_video_ids")

    @classmethod
    def get(cls):
        return cache.get("cs2015_team03_all_videos")

    @classmethod
    def has_id(cls, video_id):
        video_ids = cache.get("cs2015_team03_all_video_ids")
        if video_ids is None:
            return None

        return video_id in video_ids

    @classmethod
    def set(cls, video_list):
        cache.set("cs2015_team03_all_videos", video_list, timeout=5 * 60)

        # cache the video IDs
        video_ids = set()
        for video in video_list:
            video_ids.add(video.video_id)
        cache.set("cs2015_team03_all_video_ids", video_ids, timeout=5 * 60)


# Caching the segment list.
class SegmentListCache(object):
    @classmethod
    def get_cache_key(cls, video_id):
        return "cs2015_team03_%s_segments" % video_id

    @classmethod
    def clear(cls, video_id):
        cache.delete(cls.get_cache_key(video_id))

    @classmethod
    def get(cls, video_id):
        return cache.get(cls.get_cache_key(video_id))

    @classmethod
    def set(cls, video_id, segments):
        cache.set(cls.get_cache_key(video_id), segments, timeout=5 * 60)


# clear the relevant caches when data is changed
def on_data_changed(target, value, oldvalue):
    VideoListCache.clear()

    if isinstance(oldvalue, Video):
        SegmentListCache.clear(oldvalue.video_id)


event.listen(CsMixin, 'after_insert', on_data_changed, propagate=True)
event.listen(CsMixin, 'after_update', on_data_changed, propagate=True)
event.listen(CsMixin, 'after_delete', on_data_changed, propagate=True)

if __name__ == "__main__":
    from sqlalchemy import create_engine

    engine = create_engine(DB_URI)

    print "Dropping all tables"
    Base.metadata.drop_all(engine)

    print "Creating all tables"
    Base.metadata.create_all(engine)
