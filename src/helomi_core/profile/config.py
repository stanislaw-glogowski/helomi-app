from helomi_common import BaseConfig

from .profile import Profile


class ProfileSettings(BaseConfig):
    default: str = Profile.DEFAULT_ID
