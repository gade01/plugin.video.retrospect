# coding:UTF-8
import datetime

# import contextmenu
import chn_class
import mediaitem
from parserdata import ParserData
from helpers.datehelper import DateHelper
from streams.m3u8 import M3u8
from urihandler import UriHandler
from helpers.jsonhelper import JsonHelper

from logger import Logger


class Channel(chn_class.Channel):
    def __init__(self, channelInfo):
        """Initialisation of the class.

        Arguments:
        channelInfo: ChannelInfo - The channel info object to base this channel on.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        """

        chn_class.Channel.__init__(self, channelInfo)

        # ============== Actual channel setup STARTS here and should be overwritten from derived classes ===============
        self.useAtom = False  # : The atom feeds just do not give all videos
        self.noImage = "nrknoimage.png"

        # setup the urls
        self.mainListUri = "#mainlist"
        self.baseUrl = "http://m.nrk.no/tvapi/v1"
        self.httpHeaders["app-version-android"] = "60"

        #self.swfUrl = "%s/public/swf/video/svtplayer-2013.23.swf" % (self.baseUrl,)

        self._AddDataParser(self.mainListUri, preprocessor=self.CreateMainList)
        self._AddDataParser("http://m.nrk.no/tvapi/v1/channels", json=True,
                            parser=(),
                            creator=self.CreateLiveChannel)
        self._AddDataParser("http://m.nrk.no/tvapi/v1/series/", json=True, matchType=ParserData.MatchExact,
                            parser=(),
                            creator=self.CreateProgramFolder)

        self._AddDataParser("http://m.nrk.no/tvapi/v1/series/[^/]+", json=True, matchType=ParserData.MatchRegex,
                            parser=("programs", ),
                            creator=self.CreateCategoryVideo)

        self._AddDataParser("http://m.nrk.no/tvapi/v1/categories/all-programs/", json=True,
                            parser=(),
                            creator=self.CreateCategoryVideo)

        self._AddDataParser("*", updater=self.UpdateVideoItem)

        # ==============================================================================================================
        # non standard items

        # ==============================================================================================================
        # Test cases:

        # ====================================== Actual channel setup STOPS here =======================================
        return

    def CreateMainList(self, data):
        """Performs pre-process actions for data processing

        Arguments:
        data : string - the retrieve data that was loaded for the current item and URL.

        Returns:
        A tuple of the data and a list of MediaItems that were generated.


        Accepts an data from the ProcessFolderList method, BEFORE the items are
        processed. Allows setting of parameters (like title etc) for the channel.
        Inside this method the <data> could be changed and additional items can
        be created.

        The return values should always be instantiated in at least ("", []).

        """

        Logger.Info("Performing Pre-Processing")
        items = []

        links = {
            "Live streams": "http://m.nrk.no/tvapi/v1/channels",
            "Recommended": "http://m.nrk.no/tvapi/v1/categories/all-programs/recommendedprograms",
            "Popular": "http://m.nrk.no/tvapi/v1/categories/all-programs/popularprograms",
            "Recent": "http://m.nrk.no/tvapi/v1/categories/all-programs/recentlysentprograms",
            "Categories": "http://m.nrk.no/tvapi/v1/categories/",
            "Programs": "http://m.nrk.no/tvapi/v1/series/",
        }
        for name, url in links.iteritems():
            item = mediaitem.MediaItem(name, url)
            item.icon = self.icon
            item.thumb = self.noImage
            item.complete = True
            item.HttpHeaders = self.httpHeaders
            items.append(item)

        Logger.Debug("Pre-Processing finished")
        return data, items

    def CreateLiveChannel(self, resultSet):
        """Creates a MediaItem of type 'video' using the resultSet from the regex.

        Arguments:
        resultSet : tuple (string) - the resultSet of the self.videoItemRegex

        Returns:
        A new MediaItem of type 'video' or 'audio' (despite the method's name)

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.UpdateVideoItem method is called if the item is focussed or selected
        for playback.

        """

        Logger.Trace(resultSet)

        title = resultSet["title"]
        url = resultSet["mediaUrl"]
        item = mediaitem.MediaItem(title, url)
        item.type = 'video'
        item.isLive = True

        thumbId = resultSet.get("imageId", None)
        if thumbId is not None:
            item.thumb = "http://m.nrk.no/img?kaleidoId=%s&width=720" % (thumbId, )
        item.icon = self.icon
        item.complete = False
        return item

    def CreateProgramFolder(self, resultSet):
        """Creates a MediaItem of type 'folder' using the resultSet from the regex.

        Arguments:
        resultSet : tuple(strig) - the resultSet of the self.folderItemRegex

        Returns:
        A new MediaItem of type 'folder'

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        """

        Logger.Trace(resultSet)
        title = resultSet["title"]
        seriesId = resultSet.get("seriesId")

        item = mediaitem.MediaItem(title, "%s/series/%s" % (self.baseUrl, seriesId))
        item.icon = self.icon
        item.type = 'folder'
        item.fanart = self.fanart
        item.HttpHeaders = self.httpHeaders

        imageId = resultSet.get("imageId", None)
        if imageId is not None:
            item.thumb = "http://m.nrk.no/img?kaleidoId=%s&width=720" % (imageId, )
            item.fanart = "http://m.nrk.no/img?kaleidoId=%s&width=1280" % (imageId, )
        return item

    def CreateCategoryVideo(self, resultSet):
        """Creates a MediaItem of type 'folder' using the resultSet from the regex.

        Arguments:
        resultSet : tuple(strig) - the resultSet of the self.folderItemRegex

        Returns:
        A new MediaItem of type 'folder'

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        """

        Logger.Trace(resultSet)

        title = resultSet["title"]
        url = resultSet.get("mediaUrl", None)
        if url is None:
            url = resultSet.get("programId", None)
            if url is None:
                return None
            url = "%s/programs/%s" % (self.baseUrl, url)

        item = mediaitem.MediaItem(title, url)
        item.description = resultSet.get("description", "")
        item.icon = self.icon
        item.type = 'video'
        item.fanart = self.parentItem.fanart
        item.HttpHeaders = self.httpHeaders

        imageId = resultSet.get("imageId", None)
        if imageId is not None:
            item.thumb = "http://m.nrk.no/img?kaleidoId=%s&width=720" % (imageId, )

        fanartId = resultSet.get("seriesImageId", None)
        if fanartId is not None:
            item.fanart = "http://m.nrk.no/img?kaleidoId=%s&width=1280" % (fanartId, )

        if "usageRights" in resultSet:
            item.isGeoLocked = resultSet["usageRights"].get("geoblocked", False)
            if "availableFrom" in resultSet["usageRights"]:
                timeStamp = int(resultSet["usageRights"]["availableFrom"]) / 1000
                date = datetime.datetime.fromtimestamp(timeStamp)
                item.SetDate(date.year, date.month, date.day, date.hour, date.minute, date.second)

        return item

    def UpdateVideoItem(self, item):
        """Updates an existing MediaItem with more data.

        Arguments:
        item : MediaItem - the MediaItem that needs to be updated

        Returns:
        The original item with more data added to it's properties.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        """

        Logger.Debug('Starting UpdateVideoItem for %s (%s)', item.name, self.channelName)
        url = item.url
        if ".m3u8" not in item.url:
            data = UriHandler.Open(url, proxy=self.proxy, additionalHeaders=item.HttpHeaders)
            json = JsonHelper(data)
            url = json.GetValue("mediaUrl")
            if url is None:
                Logger.Warning("Could not find mediaUrl in %s", item.url)
                return

        spoofIp = self._GetSetting("spoof_ip", "0.0.0.0")
        if spoofIp is not None:
            item.HttpHeaders["X-Forwarded-For"] = spoofIp

        part = item.CreateNewEmptyMediaPart()
        for s, b in M3u8.GetStreamsFromM3u8(url, self.proxy, headers=item.HttpHeaders):
            item.complete = True
            # s = self.GetVerifiableVideoUrl(s)
            part.AppendMediaStream(s, b)
            if spoofIp is not None:
                part.HttpHeaders["X-Forwarded-For"] = spoofIp

        return item

    def __GetDate(self, first, second, third):
        """ Tries to parse formats for dates like "Today 9:00" or "mon 9 jun" or "Tonight 9.00"

        @param first: First part
        @param second: Second part
        @param third: Third part

        @return:  a tuple containing: year, month, day, hour, minutes
        """

        Logger.Trace("Determining date for: ('%s', '%s', '%s')", first, second, third)
        hour = minutes = 0

        year = DateHelper.ThisYear()
        if first.lower() == "idag" or first.lower() == "ikv&auml;ll":  # Today or Tonight
            date = datetime.datetime.now()
            month = date.month
            day = date.day
            hour = second
            minutes = third

        elif first.lower() == "ig&aring;r":  # Yesterday
            date = datetime.datetime.now() - datetime.timedelta(1)
            month = date.month
            day = date.day
            hour = second
            minutes = third

        elif second.isdigit():
            day = int(second)
            month = DateHelper.GetMonthFromName(third, "se")
            year = DateHelper.ThisYear()

            # if the date was in the future, it must have been last year.
            result = datetime.datetime(year, month, day)
            if result > datetime.datetime.now() + datetime.timedelta(1):
                Logger.Trace("Found future date, setting it to one year earlier.")
                year -= 1

        elif first.isdigit() and third.isdigit() and not second.isdigit():
            day = int(first)
            month = DateHelper.GetMonthFromName(second, "se")
            year = int(third)

        else:
            Logger.Warning("Unknonw date format: ('%s', '%s', '%s')", first, second, third)
            year = month = day = hour = minutes = 0

        return year, month, day, hour, minutes
