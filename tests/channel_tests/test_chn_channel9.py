# SPDX-License-Identifier: GPL-3.0-or-later

from . channeltest import ChannelTest


class TestChannel9Channel(ChannelTest):
    # noinspection PyPep8Naming
    def __init__(self, methodName):  # NOSONAR
        super(TestChannel9Channel, self).__init__(methodName, "channel.videos.channel9", "channel9")

    def test_channel_exists(self):
        self.assertIsNotNone(self.channel)

    def test_channel_main_list(self):
        items = self.channel.process_folder_list(None)
        self.assertGreaterEqual(len(items), 6)

    def test_channel_shows_folder(self):
        url = "https://channel9.msdn.com/Browse/AllShows?sort=atoz"
        self._test_folder_url(url, expected_results=16, exact_results=True)

    def test_channel_show_folder(self):
        url = "https://channel9.msdn.com/Shows/5-Things"
        self._test_folder_url(url, expected_results=5)

    def test_channel_event_folder(self):
        url = "https://channel9.msdn.com/Browse/Events?sort=atoz"
        self._test_folder_url(url, expected_results=8)

    def test_channel_subevent_folder(self):
        url = "https://channel9.msdn.com/Events/Build"
        self._test_folder_url(url, expected_results=8)

    def test_channel_video_resolving(self):
        url = "https://channel9.msdn.com/Shows/5-Things/Five-Things-About-Azure-Functions"
        self._test_video_url(url)
