# SPDX-License-Identifier: GPL-3.0-or-later

import os
import unittest

from . channeltest import ChannelTest


class TestNickelodeonChannel(ChannelTest):
    # noinspection PyPep8Naming
    def __init__(self, methodName):  # NOSONAR
        super(TestNickelodeonChannel, self).__init__(methodName, "channel.nick.nickelodeon", "nickno")

    def test_channel_exists(self):
        self.assertIsNotNone(self.channel)

    def test_main_list(self):
        items = self.channel.process_folder_list(None)
        self.assertGreaterEqual(len(items), 20, "No items found in mainlist")

    def test_mtv_nl(self):
        from resources.lib.helpers.channelimporter import ChannelIndex
        chn = ChannelIndex.get_register().get_channel(self._channel, "mtvnl")
        self.assertIsNotNone(chn)
        self.assertEqual("mtvnl", chn.channelCode)

    def test_mtv_nl_list(self):
        from resources.lib.helpers.channelimporter import ChannelIndex
        chn = ChannelIndex.get_register().get_channel(self._channel, "mtvnl")
        items = chn.process_folder_list(None)
        self.assertGreater(len(items), 50)

    def test_show_list_more_pages(self):
        url = "https://www.nickelodeon.no/shows/tawzng/familien-thunderman"
        self._test_folder_url(url, expected_results=2)

    def test_show_list_with_seasons(self):
        url = "https://www.nickelodeon.no/shows/q03fvj/avatar-legenden-om-aang"
        items = self._test_folder_url(url, expected_results=2)
        seasons = [i for i in items if i.is_folder]
        self.assertGreaterEqual(len(seasons), 1)

    def test_season_listing_no(self):
        url = "https://www.nickelodeon.no/shows/q03fvj/avatar-legenden-om-aang"
        self._test_folder_url(url, expected_results=2)

    def test_season_listing_nl(self):
        url = "https://www.nickelodeon.no/shows/76ypv4/svampebob-firkant"
        self._test_folder_url(url, expected_results=2)

    @unittest.skipIf("CI" in os.environ, "Skipping in CI due to Geo-Restrictions")
    def test_video(self):
        self._switch_channel("nickelodeon")
        url = "https://www.nickelodeon.nl/episodes/0gravl/spongebob-hole-in-one-sentimentele-troep-seizoen-seasonnumber-8-afl-3"
        self._test_video_url(url)
