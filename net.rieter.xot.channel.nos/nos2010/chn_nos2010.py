import datetime
import re

import chn_class

from logger import Logger
from regexer import Regexer
from helpers import subtitlehelper
from helpers.jsonhelper import JsonHelper
from streams.npostream import NpoStream
from streams.mpd import Mpd
from urihandler import UriHandler
from helpers.datehelper import DateHelper
from parserdata import ParserData
from helpers.languagehelper import LanguageHelper
from helpers.htmlentityhelper import HtmlEntityHelper
from vault import Vault
from addonsettings import AddonSettings
from mediaitem import MediaItem
from xbmcwrapper import XbmcWrapper


class Channel(chn_class.Channel):
    """
    main class from which all channels inherit
    """

    def __init__(self, channel_info):
        """ Initialisation of the class.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        :param ChannelInfo channel_info: The channel info object to base this channel on.

        """

        chn_class.Channel.__init__(self, channel_info)

        # ============== Actual channel setup STARTS here and should be overwritten from derived classes ===============
        self.noImage = "nosimage.png"

        # setup the urls
        if self.channelCode == "uzgjson":
            self.baseUrl = "https://apps-api.uitzendinggemist.nl"
            self.mainListUri = "#mainlist"
            self.noImage = "nosimage.png"
        else:
            raise NotImplementedError("Code %s is not implemented" % (self.channelCode,))

        # mainlist stuff
        self._add_data_parser("#mainlist", preprocessor=self.get_initial_folder_items)

        # live stuff
        self.baseUrlLive = "https://www.npostart.nl"

        # live radio, the folders and items
        self._add_data_parser("http://radio-app.omroep.nl/player/script/",
                              name="Live Radio Streams",
                              preprocessor=self.extract_json_for_live_radio, json=True,
                              parser=[], creator=self.create_live_radio)

        self._add_data_parser("/live", match_type=ParserData.MatchEnd,
                              name="Main Live Stream HTML parser",
                              preprocessor=self.get_additional_live_items,
                              parser=r'<a href="[^"]+/live/([^"]+)" class="npo-tile-link"[^>]+>[\w\W]{0,1000}?<img data-src="([^"]+)"[\w\W]{0,1000}?<h2>(?:Nu: )?([^<]+)</h2>\W+<p>(?:Straks: )?([^<]*)</p>',
                              creator=self.create_live_tv,
                              updater=self.update_video_item_live)

        self._add_data_parser("https://www.npostart.nl/live/", name="Live Video Updater from HTML",
                              updater=self.update_video_item_live)

        # Use old urls with new Updater
        self._add_data_parser("http://e.omroep.nl/metadata/", name="e.omroep.nl classic parser",
                              updater=self.update_from_poms)

        # Standard updater
        self._add_data_parser("*",
                              updater=self.update_video_item)

        # recent and popular stuff and other Json data
        self._add_data_parser(".json", name="JSON List Parser for the recent/tips/populair",
                              parser=[], creator=self.create_video_item_json,
                              json=True, match_type=ParserData.MatchEnd)

        self._add_data_parser("#recent", name="Recent items list",
                              preprocessor=self.add_recent_items)

        # Alpha listing and paging for that list
        self._add_data_parser("#alphalisting", preprocessor=self.alpha_listing)

        episode_parser = Regexer.from_expresso(
            r'id="(?<powid>[^"]+)"[^>]*>\W*<a href="(?<url>[^"]+)" title="(?<title>[^"]+)"[^>]+\W+'
            r'<div[^(>]+>\s*(?:<img[^>]+data-src="(?<thumburl>[^"]+)")?')
        self._add_data_parsers(["https://www.npostart.nl/media/series?page=", ],
                               name="Parser for main series overview pages",
                               preprocessor=self.extract_tiles,
                               parser=episode_parser,
                               creator=self.create_episode_item)

        # very similar parser as the Live Channels!
        video_parser = Regexer.from_expresso(
            r'<div[^>]+class="(?<class>[^"]+)"[^>]+id="(?<powid>[^"]+)"[^>]*>\W*<a href="[^"]+/'
            r'(?<url>[^/"]+)" class="npo-tile-link"[^>]+data-scorecard=\'(?<videodata>[^\']*)\''
            r'[^>]*>\W+<div[^>]+>\W+<div [^>]+data-from="(?<date>[^"]*)"[\w\W]{0,1000}?<img[^>]+'
            r'data-src="(?<thumburl>[^"]+)"[\w\W]{0,1000}?<h2>(?<title>[^<]+)</h2>\W+<p>'
            r'(?<subtitle>[^<]*)</p>')
        self._add_data_parsers(["https://www.npostart.nl/media/series/",
                                "https://www.npostart.nl/search/extended",
                                "https://www.npostart.nl/media/collections/"],
                               name="Parser for shows on the main series sub pages, the search and the genres",
                               preprocessor=self.extract_tiles,
                               parser=video_parser,
                               creator=self.create_npo_item)

        # Genres
        self._add_data_parser("https://www.npostart.nl/programmas",
                              match_type=ParserData.MatchExact,
                              name="Genres",
                              parser=r'<a\W+class="close-dropdown"\W+href="/collectie/([^"]+)"\W+'
                                     r'title="([^"]+)"[^>]+data-value="([^"]+)"[^>]+'
                                     r'data-argument="genreId',
                              creator=self.create_genre_item)

        # Favourites
        self._add_data_parser("https://www.npostart.nl/ums/accounts/@me/favourites",
                              preprocessor=self.extract_tiles,
                              parser=episode_parser,
                              creator=self.create_episode_item,
                              requires_logon=True)

        # Alpha listing based on JSON API
        self._add_data_parser("https://start-api.npo.nl/page/catalogue", json=True,
                              parser=["components", 1, "data", "items"],
                              creator=self.create_json_episode_item)

        # New API endpoints:
        # https://start-api.npo.nl/epg/2018-12-22?type=tv
        # https://start-api.npo.nl/page/catalogue?az=C&pageSize=1000
        # https://start-api.npo.nl/page/catalogue?pageSize=0
        # https://start-api.npo.nl/page/catalogue?pageSize=500
        # https://start-api.npo.nl/search?query=sinterklaas&pageSize=1000

        tv_guide_regex = r'data-channel="(?<channel>[^"]+)"[^>]+data-title="(?<title>[^"]+)"[^>]+' \
                         r'data-id=\'(?<url>[^\']+)\'[^>]*>\W*<div[^>]*>\W+<p>\W+<span[^>]+time"' \
                         r'[^>]*>(?<hours>\d+):(?<minutes>\d+)</span>\W+<span[^<]+</span>\W+<span ' \
                         r'class="npo-epg-active"></span>\W+<span class="npo-epg-play"></span>'
        tv_guide_regex = Regexer.from_expresso(tv_guide_regex)
        self._add_data_parser("https://www.npostart.nl/gids?date=",
                              parser=tv_guide_regex, creator=self.create_tv_guide_item)

        self.__ignore_cookie_law()

        # ===============================================================================================================
        # non standard items
        self.__NextPageAdded = False

        # ====================================== Actual channel setup STOPS here =======================================
        return

    def log_on(self):
        """ Makes sure that we are logged on. """

        username = self._get_setting("username")
        if not username:
            Logger.info("No user name for NPO, not logging in")
            return False

        cookie = UriHandler.get_cookie("isAuthenticatedUser", "www.npostart.nl")
        if cookie:
            expire_date = DateHelper.get_date_from_posix(float(cookie.expires))
            Logger.info("Found existing valid NPO token (valid until: %s)", expire_date)
            return True

        v = Vault()
        password = v.get_channel_setting(self.guid, "password")

        # get a token (why?), cookies and an xsrf token
        token = UriHandler.open("https://www.npostart.nl/api/token", proxy=self.proxy, no_cache=True,
                                additional_headers={"X-Requested-With": "XMLHttpRequest"})

        json_token = JsonHelper(token)
        token = json_token.get_value("token")
        if not token:
            return False
        xsrf_token = UriHandler.get_cookie("XSRF-TOKEN", "www.npostart.nl").value
        xsrf_token = HtmlEntityHelper.url_decode(xsrf_token)

        data = "username=%s&password=%s" % (HtmlEntityHelper.url_encode(username),
                                            HtmlEntityHelper.url_encode(password))
        UriHandler.open("https://www.npostart.nl/api/login", proxy=self.proxy, no_cache=True,
                        additional_headers={
                            "X-Requested-With": "XMLHttpRequest",
                            "X-XSRF-TOKEN": xsrf_token
                        },
                        params=data)

        # The cookie should already be in the jar now
        return True

    def extract_tiles(self, data):  # NOSONAR
        """ Extracts the JSON tiles data from the HTML.

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        items = []
        new_data = ""

        json_data = JsonHelper(data)
        tiles = json_data.get_value("tiles")
        if not isinstance(tiles, (tuple, list)):
            Logger.debug("Found single tile data blob")
            new_data = tiles
        else:
            Logger.debug("Found multiple tile data blobs")
            for item_data in tiles:
                new_data = "%s%s\n" % (new_data, item_data)

        # More pages?
        max_count = 5
        current_count = 1
        next_page = json_data.get_value("nextLink")
        query_string = self.parentItem.url.split("&", 1)[-1]

        http_headers = {"X-Requested-With": "XMLHttpRequest"}
        http_headers.update(self.parentItem.HttpHeaders)
        http_headers.update(self.httpHeaders)
        while next_page and current_count < max_count:
            current_count += 1
            Logger.debug("Found next page: %s", next_page)
            if next_page.startswith("/search/extended") or next_page.startswith("/media/series"):
                next_page = next_page.split("&", 1)[0]
                next_page = "%s%s&%s" % (self.baseUrlLive, next_page, query_string)
            elif not next_page.startswith("http"):
                next_page = "%s%s&%s" % (self.baseUrlLive, next_page, query_string)
            else:
                next_page = "%s&%s" % (next_page, query_string)

            page_data = UriHandler.open(next_page, proxy=self.proxy, additional_headers=http_headers)
            json_data = JsonHelper(page_data)
            tiles = json_data.get_value("tiles")
            if not isinstance(tiles, (tuple, list)):
                Logger.debug("Found single tile data blob")
                new_data = "%s%s\n" % (new_data, tiles)
            else:
                Logger.debug("Found multiple tile data blobs")
                for item_data in tiles:
                    new_data = "%s%s\n" % (new_data, item_data)
            next_page = json_data.get_value("nextLink")

        if next_page and current_count == max_count:
            # There are more pages
            if next_page.startswith("/search/extended") or next_page.startswith("/media/series"):
                next_page = next_page.split("&", 1)[0]
                next_page = "%s%s&%s" % (self.baseUrlLive, next_page, query_string)
            elif not next_page.startswith("http"):
                next_page = "%s%s&%s" % (self.baseUrlLive, next_page, query_string)
            else:
                next_page = "%s&%s" % (next_page, query_string)

            title = LanguageHelper.get_localized_string(LanguageHelper.MorePages)
            title = "\a.: %s :." % (title,)
            more = MediaItem(title, next_page)
            more.thumb = self.parentItem.thumb
            more.fanart = self.parentItem.fanart
            more.HttpHeaders = http_headers
            more.HttpHeaders.update(self.parentItem.HttpHeaders)
            items.append(more)

        return new_data, items

    def get_initial_folder_items(self, data):
        """ Creates the initial folder items for this channel.

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        items = []
        search = MediaItem("Zoeken", "searchSite")
        search.complete = True
        search.icon = self.icon
        search.thumb = self.noImage
        search.dontGroup = True
        search.set_date(2200, 1, 1, text="")
        search.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        items.append(search)

        # Favorite items that require login
        # favs = MediaItem("Favorieten", "https://www.npostart.nl/ums/accounts/@me/favourites?page=1&type=series&tileMapping=normal&tileType=teaser")
        # favs.complete = True
        # favs.description = "Favorieten van de NPO.nl website. Het toevoegen van favorieten " \
        #                    "wordt nog niet ondersteund."
        # favs.icon = self.icon
        # favs.thumb = self.noImage
        # favs.dontGroup = True
        # favs.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        # favs.set_date(2200, 1, 1, text="")
        # items.append(favs)

        extra = MediaItem("Live Radio", "http://radio-app.omroep.nl/player/script/player.js")
        extra.complete = True
        extra.icon = self.icon
        extra.thumb = self.noImage
        extra.dontGroup = True
        extra.set_date(2200, 1, 1, text="")
        items.append(extra)

        extra = MediaItem("Live TV", "%s/live" % (self.baseUrlLive,))
        extra.complete = True
        extra.icon = self.icon
        extra.thumb = self.noImage
        extra.dontGroup = True
        extra.set_date(2200, 1, 1, text="")
        items.append(extra)

        extra = MediaItem("Programma's (Hele lijst)",
                          "https://start-api.npo.nl/page/catalogue?pageSize=500")
        extra.complete = True
        extra.icon = self.icon
        extra.thumb = self.noImage
        extra.dontGroup = True
        extra.description = "Volledige programma lijst van NPO Start."
        extra.set_date(2200, 1, 1, text="")
        extra.HttpHeaders["Apikey"] = "e45fe473feaf42ad9a215007c6aa5e7e"
        # API Key from here: https://packagist.org/packages/kro-ncrv/npoplayer?q=&p=0&hFR%5Btype%5D%5B0%5D=concrete5-package
        items.append(extra)

        extra = MediaItem("Genres", "https://www.npostart.nl/programmas")
        extra.complete = True
        extra.icon = self.icon
        extra.thumb = self.noImage
        extra.dontGroup = True
        extra.set_date(2200, 1, 1, text="")
        items.append(extra)

        extra = MediaItem("Programma's (A-Z)", "#alphalisting")
        extra.complete = True
        extra.icon = self.icon
        extra.thumb = self.noImage
        extra.description = "Alfabetische lijst van de NPO.nl site."
        extra.dontGroup = True
        extra.set_date(2200, 1, 1, text="")
        items.append(extra)

        recent = MediaItem("Recent", "#recent")
        recent.complete = True
        recent.icon = self.icon
        recent.thumb = self.noImage
        recent.dontGroup = True
        recent.set_date(2200, 1, 1, text="")
        items.append(recent)

        return data, items

    def add_recent_items(self, data):
        """ Builds the "Recent" folder for this channel.

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        items = []
        today = datetime.datetime.now()
        days = ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"]
        for i in range(0, 7, 1):
            air_date = today - datetime.timedelta(i)
            Logger.trace("Adding item for: %s", air_date)

            # Determine a nice display date
            day = days[air_date.weekday()]
            if i == 0:
                day = "Vandaag"
            elif i == 1:
                day = "Gisteren"
            elif i == 2:
                day = "Eergisteren"
            title = "%04d-%02d-%02d - %s" % (air_date.year, air_date.month, air_date.day, day)

            # url = "https://www.npostart.nl/media/series?page=1&dateFrom=%04d-%02d-%02d&tileMapping=normal&tileType=teaser&pageType=catalogue" % \
            url = "https://www.npostart.nl/gids?date=%04d-%02d-%02d&type=tv" % \
                  (air_date.year, air_date.month, air_date.day)
            extra = MediaItem(title, url)
            extra.complete = True
            extra.icon = self.icon
            extra.thumb = self.noImage
            extra.dontGroup = True
            extra.HttpHeaders["X-Requested-With"] = "XMLHttpRequest"
            extra.HttpHeaders["Accept"] = "text/html, */*; q=0.01"
            extra.set_date(air_date.year, air_date.month, air_date.day, text="")

            items.append(extra)

        return data, items

    def get_additional_live_items(self, data):
        """ Adds some missing live items to the list of live items.

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        Logger.info("Processing Live items")

        items = []
        if self.parentItem.url.endswith("/live"):
            # let's add the 3FM live stream
            parent = self.parentItem

            live_streams = {
                "3FM Live": {
                    "url": "http://e.omroep.nl/metadata/LI_3FM_300881",
                    "thumb": "http://www.3fm.nl/data/thumb/abc_media_image/113000/113453/w210.1b764.jpg"
                },
                "Radio 2 Live": {
                    "url": "http://e.omroep.nl/metadata/LI_RADIO2_300879",
                    "thumb": self.get_image_location("radio2.png")
                    # "thumb": "http://www.radio2.nl/image/rm/48254/NPO_RD2_Logo_RGB_1200dpi.jpg?width=848&height=477"
                },
                "Radio 6 Live": {
                    "url": "http://e.omroep.nl/metadata/LI_RADIO6_300883",
                    # "thumb": "http://www.radio6.nl/data/thumb/abc_media_image/3000/3882/w500.1daa0.png"
                    "thumb": self.get_image_location("radio6.png")
                },
                "Radio 1 Live": {
                    "url": "http://e.omroep.nl/metadata/LI_RADIO1_300877",
                    # "thumb": "http://statischecontent.nl/img/tweederdevideo/1e7db3df-030a-4e5a-b2a2-840bd0fd8242.jpg"
                    "thumb": self.get_image_location("radio1.png")
                },
            }

            for stream in live_streams:
                Logger.debug("Adding video item to '%s' sub item list: %s", parent, stream)
                live_data = live_streams[stream]
                item = MediaItem(stream, live_data["url"])
                item.icon = parent.icon
                item.thumb = live_data["thumb"]
                item.type = 'video'
                item.isLive = True
                item.complete = False
                items.append(item)
        return data, items

    def extract_json_for_live_radio(self, data):
        """ Extracts the JSON data from the HTML for the radio streams

        @param data: the HTML data
        @return:     a valid JSON string and no items

        """

        items = []
        data = Regexer.do_regex(r'NPW.config.channels\s*=\s*([\w\W]+?),\s*NPW\.config\.', data)[-1].rstrip(";")
        # fixUp some json
        data = re.sub(r'(\w+):([^/])', '"\\1":\\2', data)
        Logger.trace(data)
        return data, items

    def alpha_listing(self, data):
        """ Creates a alpha listing with items pointing to the alpha listing on line.

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        Logger.info("Generating an Alpha list for NPO")

        items = []
        # https://www.npostart.nl/media/series?page=1&dateFrom=2014-01-01&tileMapping=normal&tileType=teaser
        # https://www.npostart.nl/media/series?page=2&dateFrom=2014-01-01&az=A&tileMapping=normal&tileType=teaser
        # https://www.npostart.nl/media/series?page=2&dateFrom=2014-01-01&az=0-9&tileMapping=normal&tileType=teaser

        title_format = LanguageHelper.get_localized_string(LanguageHelper.StartWith)
        url_format = "https://www.npostart.nl/media/series?page=1&dateFrom=2014-01-01&az=%s&tileMapping=normal&tileType=teaser&pageType=catalogue"
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0":
            if char == "0":
                char = "0-9"
            sub_item = MediaItem(title_format % (char,), url_format % (char,))
            sub_item.complete = True
            sub_item.icon = self.icon
            sub_item.thumb = self.noImage
            sub_item.dontGroup = True
            sub_item.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
            items.append(sub_item)
        return data, items

    def create_episode_item(self, result_set):
        """ Creates a new MediaItem for an episode.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'folder'.
        :rtype: MediaItem|None

        """

        item = chn_class.Channel.create_episode_item(self, result_set)

        # Update the URL
        # https://www.npostart.nl/media/series/POW_03094258/episodes?page=2&tileMapping=dedicated&tileType=asset
        url = "https://www.npostart.nl/media/series/%(powid)s/episodes?page=1&tileMapping=dedicated&tileType=asset&pageType=franchise" % result_set
        item.url = url
        item.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        item.dontGroup = True
        return item

    def create_json_episode_item(self, result_set):
        """ Creates a new MediaItem for an episode.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'folder'.
        :rtype: MediaItem|None

        """

        Logger.trace(result_set)
        if not result_set:
            return None

        # if we should not use the mobile listing and we have a non-mobile ID)
        if 'id' in result_set:
            url = "https://www.npostart.nl/media/series/{id}/episodes?page=1&tileMapping=dedicated&tileType=asset&pageType=franchise".format(**result_set)
        else:
            Logger.warning("Skipping (no '(m)id' ID): %(title)s", result_set)
            return None

        name = result_set['title']
        description = result_set.get('description', '')

        item = MediaItem(name, url)
        item.type = 'folder'
        item.icon = self.icon
        item.complete = True
        item.description = description
        item.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        # This should always be a full list as we already have a default alphabet listing available
        # from NPO
        item.dontGroup = True

        if "images" not in result_set:
            return item

        images = result_set["images"]
        for image_type, image_data in images.items():
            if image_type == "original" and "tv" in image_data["formats"]:
                    item.fanart = image_data["formats"]["tv"]["source"]
            elif image_type == "grid.tile":
                item.thumb = image_data["formats"]["tv"]["source"]

        return item

    # noinspection PyUnusedLocal
    def search_site(self, url=None):  # @UnusedVariable
        """ Creates an list of items by searching the site.

        This method is called when the URL of an item is "searchSite". The channel
        calling this should implement the search functionality. This could also include
        showing of an input keyboard and following actions.

        The %s the url will be replaced with an URL encoded representation of the
        text to search for.

        :param str url:     Url to use to search with a %s for the search parameters.

        :return: A list with search results as MediaItems.
        :rtype: list[MediaItem]

        """

        # The Videos
        url = "https://www.npostart.nl/search/extended?page=1&query=%s&filter=episodes&dateFrom=2014-01-01&tileMapping=search&tileType=asset&pageType=search"

        # The Shows
        # url = "https://www.npostart.nl/search/extended?page=1&query=%s&filter=programs&dateFrom=2014-01-01&tileMapping=normal&tileType=teaser&pageType=search"

        self.httpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        return chn_class.Channel.search_site(self, url)

    def create_tv_guide_item(self, result_set):
        """ Creates a MediaItem of type 'video' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        Logger.trace(result_set)
        channel = result_set["channel"].replace("NED", "NPO ")
        title = "{0[hours]}:{0[minutes]} - {1} - {0[title]}".format(result_set, channel)
        item = MediaItem(title, result_set["url"])
        item.icon = self.icon
        item.description = result_set["channel"]
        item.type = 'video'
        item.fanart = self.fanart
        item.HttpHeaders = self.httpHeaders
        item.complete = False
        return item

    def create_npo_item(self, result_set):
        """ Creates a generic NPO MediaItem of type 'video' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        item = chn_class.Channel.create_video_item(self, result_set)

        # set the POW id
        if result_set["videodata"]:
            item.type = "video"
            item.url = result_set["powid"]
        else:
            item.type = "folder"
            item.url = "https://www.npostart.nl/media/series/%(powid)s/episodes?page=1&tileMapping=dedicated&tileType=asset&pageType=franchise" % result_set
            item.HttpHeaders = {"X-Requested-With": "XMLHttpRequest"}
        item.isPaid = "premium" in result_set["class"]

        # figure out the date
        try:
            date_time = result_set["subtitle"].strip().replace("  ", " ").split(" ")

            # For #933 we check for NOS Journaal
            if ":" in date_time[-1] and item.name == "NOS Journaal":
                item.name = "{0} - {1}".format(item.name, date_time[-1])

            if self.__determine_date_time_for_npo_item(item, date_time):
                # We don't need the subtitle as it contained the date
                # item.name = result_set["title"]   # won't work when sorting by name
                Logger.trace("Date found in subtitle: %s", result_set.get("subtitle"))

        except:
            Logger.debug("Cannot set date from label: %s", result_set.get("subtitle"), exc_info=True)
            # 2016-07-05T00:00:00Z
            date_value = result_set.get("date")
            if date_value:
                time_stamp = DateHelper.get_date_from_string(date_value, "%Y-%m-%dT%H:%M:%SZ")
                item.set_date(*time_stamp[0:6])
            else:
                Logger.warning("Cannot set date from 'data-from': %s", result_set["date"],
                               exc_info=True)

        return item

    def create_video_item_json(self, result_set):
        """ Creates a MediaItem of type 'video' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        Logger.trace(result_set)

        # In some cases the name, posix and description are in the root, in other cases in the
        # 'episode' node
        posix = result_set.get('starts_at')
        image = result_set.get('image')
        name = result_set.get('name')
        description = result_set.get('description', '')

        # the tips has an extra 'episodes' key
        if 'episode' in result_set:
            Logger.debug("Found subnode: episodes")
            # set to episode node
            data = result_set['episode']
        else:
            Logger.warning("No subnode 'episodes' found, trying anyways")
            data = result_set

        # look for better values
        posix = data.get('broadcasted_at', posix)
        # noinspection PyTypeChecker
        broadcasted = DateHelper.get_date_from_posix(posix)
        description = result_set.get('description', description)
        video_id = data.get('whatson_id')

        # try to fetch more name data
        names = []
        name = data.get("name", name)
        if name:
            names = [name, ]
        if "series" in data and "name" in data["series"]:
            # noinspection PyTypeChecker
            names.insert(0, data["series"]["name"])

        # Filter the duplicates
        title = " - ".join(set(names))

        item = MediaItem(title, video_id)
        item.icon = self.icon
        item.type = 'video'
        item.complete = False
        item.description = description
        #
        images = data.get('stills')
        if images:
            # there were images in the stills
            # noinspection PyTypeChecker
            item.thumb = images[-1]['url']
        elif image:
            # no stills, or empty, check for image
            item.thumb = image

        item.set_date(broadcasted.year, broadcasted.month, broadcasted.day, broadcasted.hour,
                      broadcasted.minute,
                      broadcasted.second)

        return item

    def create_genre_item(self, result_set):
        """ Creates a MediaItem for a genre of type 'folder' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        Logger.trace(result_set)

        url = "https://www.npostart.nl/media/collections/%s?page=1&tileMapping=normal&tileType=asset&pageType=collection" % (result_set[0],)
        item = MediaItem(result_set[1], url)
        item.thumb = self.parentItem.thumb
        item.icon = self.parentItem.icon
        item.type = 'folder'
        item.fanart = self.parentItem.fanart
        item.HttpHeaders["X-Requested-With"] = "XMLHttpRequest"
        item.complete = True
        return item

    def create_live_tv(self, result_set):
        """ Creates a MediaItem for a live item of type 'video' using the result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        Logger.trace("Content = %s", result_set)

        # first regex matched -> video channel
        channel_id = result_set[0]
        if channel_id == "<exception>":
            name = "NPO 3"
        else:
            name = result_set[0].replace("-", " ").title().replace("Npo", "NPO")

        now_playing = result_set[2]
        next_up = result_set[3]
        name = "%s: %s" % (name, now_playing)
        if next_up:
            description = "Nu: %s\nStraks om %s" % (now_playing, next_up)
        else:
            description = "Nu: %s" % (result_set[3].strip(),)

        item = MediaItem(name, "%s/live/%s" % (self.baseUrlLive, result_set[0]), type="video")
        item.description = description

        if result_set[1].startswith("http"):
            item.thumb = result_set[1].replace("regular_", "").replace("larger_", "")
        elif result_set[1].startswith("//"):
            item.thumb = "http:%s" % (result_set[1].replace("regular_", "").replace("larger_", ""),)
        else:
            item.thumb = "%s%s" % (self.baseUrlLive, result_set[1].replace("regular_", "").replace("larger_", ""))

        item.icon = self.icon
        item.complete = False
        item.isLive = True
        return item

    def create_live_radio(self, result_set):
        """ Creates a MediaItem for a live radio item of type 'video' using the
        result_set from the regex.

        This method creates a new MediaItem from the Regular Expression or Json
        results <result_set>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.update_video_item method is called if the item is focussed or selected
        for playback.

        :param list[str]|dict[str,str] result_set: The result_set of the self.episodeItemRegex

        :return: A new MediaItem of type 'video' or 'audio' (despite the method's name).
        :rtype: MediaItem|None

        """

        Logger.trace("Content = %s", result_set)
        name = result_set["name"]
        if name == "demo":
            return None

        item = MediaItem(name, "", type="audio")
        item.thumb = self.parentItem.thumb
        item.icon = self.icon
        item.isLive = True
        item.complete = False

        # noinspection PyTypeChecker
        streams = result_set.get("audiostreams", [])
        part = item.create_new_empty_media_part()

        # first check for the video streams
        # noinspection PyTypeChecker
        for stream in result_set.get("videostreams", []):
            Logger.trace(stream)
            # url = stream["url"]
            # if not url.endswith("m3u8"):
            if not stream["protocol"] == "prid":
                continue
            item.url = "http://e.omroep.nl/metadata/%(url)s" % stream
            item.complete = False
            return item

        # else the radio streams
        for stream in streams:
            Logger.trace(stream)
            if not stream["protocol"] or stream["protocol"] == "prid":
                continue
            bitrate = stream.get("bitrate", 0)
            url = stream["url"]
            part.append_media_stream(url, bitrate)
            item.complete = True
            # if not stream["protocol"] == "prid":
            #     continue
            # item.url = "http://e.omroep.nl/metadata/%(url)s" % stream
            # item.complete = False
        return item

    def update_video_item(self, item):
        """ Updates an existing MediaItem with more data.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        :param MediaItem item: the original MediaItem that needs updating.

        :return: The original item with more data added to it's properties.
        :rtype: MediaItem

        """

        if "/radio/" in item.url or "/live/" in item.url or "/LI_" in item.url:
            Logger.info("Updating Live item: %s", item.url)
            return self.update_video_item_live(item)

        whatson_id = item.url
        return self.__update_video_item(item, whatson_id)

    def update_from_poms(self, item):
        """ Updates an existing MediaItem with more data based on the POMS Id.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        :param MediaItem item: the original MediaItem that needs updating.

        :return: The original item with more data added to it's properties.
        :rtype: MediaItem

        """

        poms = item.url.split("/")[-1]
        return self.__update_video_item(item, poms)

    def update_video_item_live(self, item):
        """ Updates an existing Live MediaItem with more data.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        :param MediaItem item: the original MediaItem that needs updating.

        :return: The original item with more data added to it's properties.
        :rtype: MediaItem

        """

        Logger.debug('Starting update_video_item: %s', item.name)

        item.MediaItemParts = []
        part = item.create_new_empty_media_part()

        # we need to determine radio or live tv
        Logger.debug("Fetching live stream data from item url: %s", item.url)
        html_data = UriHandler.open(item.url, proxy=self.proxy)

        mp3_urls = Regexer.do_regex("""data-streams='{"url":"([^"]+)","codec":"[^"]+"}'""", html_data)
        if len(mp3_urls) > 0:
            Logger.debug("Found MP3 URL")
            part.append_media_stream(mp3_urls[0], 192)
        else:
            Logger.debug("Finding the actual metadata url from %s", item.url)
            # NPO3 normal stream had wrong subs
            if "npo-3" in item.url and False:
                # NPO3 has apparently switched the normal and hearing impaired streams?
                json_urls = Regexer.do_regex('<div class="video-player-container"[^>]+data-alt-prid="([^"]+)"', html_data)
            else:
                json_urls = Regexer.do_regex('<npo-player media-id="([^"]+)"', html_data)

            use_adaptive = AddonSettings.use_adaptive_stream_add_on(with_encryption=True)
            if not use_adaptive:
                XbmcWrapper.show_dialog(
                    LanguageHelper.get_localized_string(LanguageHelper.DrmTitle),
                    LanguageHelper.get_localized_string(LanguageHelper.DrmText))
                return item

            for episode_id in json_urls:
                if use_adaptive:
                    return self.__update_dash_item(item, episode_id)
                return self.__update_video_item(item, episode_id)

            Logger.warning("Cannot update live item: %s", item)
            return item

        item.complete = True
        return item

    def __update_dash_item(self, item, episode_id):
        """ Updates an existing MediaItem with more data based on Dash video encoding.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        :param MediaItem item:  the original MediaItem that needs updating.
        :param str episode_id:  the ID of the episode.

        :return: The original item with more data added to it's properties.
        :rtype: MediaItem

        """

        url = "https://start-player.npo.nl/video/{0}/streams?profile=dash-widevine&" \
              "quality=npo&streamType=livetv&mobile=0&ios=0&isChromecast=0".format(episode_id)
        dash_data = UriHandler.open(url, proxy=self.proxy)
        dash_json = JsonHelper(dash_data)
        dash_url = dash_json.get_value("stream", "src")
        dash_license_url = dash_json.get_value("stream", "keySystemOptions", 0, "options", "licenseUrl")
        dash_headers = dash_json.get_value("stream", "keySystemOptions", 0, "options", "httpRequestHeaders")
        dash_headers[u"Referer"] = unicode(url)
        dash_license = Mpd.get_license_key(dash_license_url, key_headers=dash_headers, key_type="R")

        part = item.create_new_empty_media_part()
        stream = part.append_media_stream(dash_url, 0)
        Mpd.set_input_stream_addon_input(stream, self.proxy, dash_headers, license_key=dash_license)
        item.complete = True
        return item

    def __update_video_item(self, item, episode_id):
        """ Updates an existing MediaItem with more data.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        :param MediaItem item:  the original MediaItem that needs updating.
        :param str episode_id:  the ID of the episode.

        :return: The original item with more data added to it's properties.
        :rtype: MediaItem

        """

        Logger.trace("Using Generic update_video_item method")

        # get the subtitle
        sub_title_url = "http://tt888.omroep.nl/tt888/%s" % (episode_id,)
        sub_title_path = subtitlehelper.SubtitleHelper.download_subtitle(
            sub_title_url, episode_id + ".srt", format='srt', proxy=self.proxy)

        item.MediaItemParts = []
        part = item.create_new_empty_media_part()
        part.Subtitle = sub_title_path

        if AddonSettings.use_adaptive_stream_add_on(with_encryption=True):
            NpoStream.add_mpd_stream_from_npo(None, episode_id, part, proxy=self.proxy)
            item.complete = True
        else:
            for s, b in NpoStream.get_streams_from_npo(None, episode_id, proxy=self.proxy):
                item.complete = True
                part.append_media_stream(s, b)

        return item

    def __ignore_cookie_law(self):
        """ Accepts the cookies from UZG in order to have the site available """

        Logger.info("Setting the Cookie-Consent cookie for www.uitzendinggemist.nl")

        UriHandler.set_cookie(name='site_cookie_consent', value='yes',
                              domain='.www.uitzendinggemist.nl')
        UriHandler.set_cookie(name='npo_cc', value='tmp', domain='.www.uitzendinggemist.nl')

        UriHandler.set_cookie(name='site_cookie_consent', value='yes', domain='.npo.nl')
        UriHandler.set_cookie(name='npo_cc', value='30', domain='.npo.nl')

        UriHandler.set_cookie(name='site_cookie_consent', value='yes', domain='.npostart.nl')
        UriHandler.set_cookie(name='npo_cc', value='30', domain='.npostart.nl')
        return

    def __determine_date_time_for_npo_item(self, item, date_time):
        """

        :param MediaItem item:          The current item
        :param list[str|int] date_time:     The date time string items

        :return: whether the date time was found
        :rtype: True

        """

        Logger.trace(date_time)
        if date_time[0].lower() == "gisteren":
            date_time = datetime.datetime.now() + datetime.timedelta(days=-1)
            item.set_date(date_time.year, date_time.month, date_time.day)
        elif date_time[0].lower() == "vandaag":
            date_time = datetime.datetime.now()
            item.set_date(date_time.year, date_time.month, date_time.day)
        elif ":" in date_time[-1]:
            if date_time[-2].isalpha():
                year = datetime.datetime.now().year
                date_time.insert(-1, year)
            if item.name == "NOS Journaal":
                item.name = "{0} - {1}".format(item.name, date_time[-1])
            year = int(date_time[-2])

            month = DateHelper.get_month_from_name(date_time[-3], language="nl")
            day = int(date_time[-4])

            stamp = datetime.datetime(year, month, day)
            if stamp > datetime.datetime.now():
                year -= 1
            item.set_date(year, month, day)
        else:
            # there is an actual date present
            if date_time[0].isalpha():
                # first part is ma/di/wo/do/vr/za/zo
                date_time.pop(0)

            # translate the month
            month = DateHelper.get_month_from_name(date_time[1], language="nl")

            # if the year is missing, let's assume it is this year
            if ":" in date_time[2]:
                date_time[2] = datetime.datetime.now().year
                # in the past of future, if future, we need to substract
                stamp = datetime.datetime(int(date_time[2]), month, int(date_time[0]))
                if stamp > datetime.datetime.now():
                    date_time[2] -= 1

            item.set_date(date_time[2], month, date_time[0])
        return True
