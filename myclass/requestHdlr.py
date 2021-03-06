import os, random, requests, base64, time, flask
from urllib.parse import urlencode, quote_plus
from myclass.firebaseWrapper import firebaseWrapper
from myclass.globals import GLOBALS, MESSAGE
from myclass.errorcode import CommonError, MakeError
from myclass.GooglePlaceWebAPIWrapper import GooglePlaceWebAPIWrapper,GoogleStaticMapsAPIWrapper
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError, LineBotApiError
)
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, LocationMessage,
    TextSendMessage, ImageSendMessage, TemplateSendMessage,
    ButtonsTemplate, 
    CarouselTemplate, CarouselColumn,
    PostbackTemplateAction, MessageTemplateAction, URITemplateAction,
)

app = flask.current_app

class requestHdlr(object):
    def __init__(self, event, handler, line_bot_api):
        self._event       = event
        self._hdlr        = handler
        self._line        = line_bot_api
        self._inlist      = False
        self._fb          = firebaseWrapper(GLOBALS.DATABASE_BASE_URL)
        self._sender_type = self._replySenderInfo(True)[0]
        self._sender_id   = self._replySenderInfo(True)[1]
        self._timestamp   = self._event.timestamp

        self._fb.set_db(GLOBALS.DATABASE_BASE_NAME)
        random.seed()

    def setWhiteList(self, bSwitch):
        self._inlist = bSwitch

    def dispatch(self):
        if self._event.message.type == 'text':
            self.string_command_handler()
        elif self._event.message.type == 'image':
            if self._sender_type == 'user':
                self.image_command_handler()
        elif self._event.message.type == 'location':
            self.location_command_handler()

    def location_command_handler(self):
        obj_location = GooglePlaceWebAPIWrapper(GLOBALS.GOOGLE_PLACES_API_W_SVC_KEY)
        dict_result  = obj_location.get(self._event.message.latitude,self._event.message.longitude)

        lst_carousel_column     = []
        lst_db_record_requests  = []
        while dict_result:
            luck_place = random.choice(dict_result)
            dict_result.remove(luck_place)
            try:
                the_lat = luck_place['geometry']['location']['lat']
                the_lng = luck_place['geometry']['location']['lng']
                the_name= luck_place['name']
                the_addr= luck_place['vicinity']

                navigation_uri               = 'https://www.google.com.tw/maps/place/%s,%s'%(the_lat, the_lng)
                postback_thumbnail_image_url = GoogleStaticMapsAPIWrapper(url=flask.request.base_url.replace('callback','googlemap')).get(the_lat, the_lng, the_name, self._event.reply_token)

                the_search        = ' '.join([the_addr, the_name])
                params_string     = urlencode({'q':the_search}, quote_via=quote_plus)
                google_for_it_uri = '?'.join(['https://www.google.com.tw/search', params_string])

                objCarouselColumn = CarouselColumn(
                            thumbnail_image_url=postback_thumbnail_image_url,
                            title=u'%s'%the_name,
                            text=u'%s'%the_addr,
                            actions=[
                                URITemplateAction(
                                    label=MESSAGE.MAP_NAVI_BTN,
                                    uri=navigation_uri
                                ),
                                URITemplateAction(
                                    label=MESSAGE.MAP_NAVI_SRCH,
                                    uri=google_for_it_uri
                                )
                            ]
                        )

                lst_carousel_column.append(objCarouselColumn)
                lst_db_record_requests.append({ 'id'     : len(lst_carousel_column),
                                                'center' : '%s,%s'%(the_lat, the_lng), 
                                                'name'   : the_name })

                if len(lst_carousel_column) > 2:
                    break
            except LineBotApiError as e:
                app.logger.error(luck_place)
                continue

        if len(lst_carousel_column) > 0:
            image_carousel_template_message = TemplateSendMessage(
                alt_text=MESSAGE.POST_BACK_ALT,
                template=CarouselTemplate(
                    columns=lst_carousel_column
                )
            )   

            self._line.reply_message( self._event.reply_token, image_carousel_template_message )
            self._fb.update_one({'type':'gmap_token', 
                                 'key':self._event.reply_token, 
                                 'time':self._timestamp, 
                                 'requests': lst_db_record_requests})
        else: 
            self._replyText(CommonError.NO_AVALIABLE_DATA.get_msg())

        app.logger.info('Leave location handler')

    def image_command_handler(self):
        str_image_id    = self._event.message.id
        # Reply User request
        '''
        self._line.reply_message(
            self._event.reply_token,
            TemplateSendMessage(
                alt_text=MESSAGE.POST_BACK_ALT,
                template=ButtonsTemplate(
                    title=MESSAGE.DONATE_TITLE,
                    text=MESSAGE.DONATE_IMAGE,
                    actions=[
                        PostbackTemplateAction(
                            label=MESSAGE.AGREE,
                            data='action=%s&value=%s&from=%s&timestamp=%s'%(CommonError.AGREE_TO_DONATE, str_image_id, self._sender_id, self._timestamp)
                        ),
                        PostbackTemplateAction(
                            label=MESSAGE.DISAGREE,
                            data='action=%s&value=%s&from=%s&timestamp=%s'%(CommonError.DISAGREE_TO_DONATE, str_image_id, self._sender_id, self._timestamp)
                        )
                    ]
                )
            )
        )
        '''
        # retrieve image from line server
        message_content = self._line.get_message_content(str_image_id)
        for chunk in message_content.iter_content():
            print(chunk)
        

    def string_command_handler(self):
        if GLOBALS.YOUR_NAME_OF_THE_BOT in self._event.message.text:
            self._replyText(u'有人在找%s嗎？'%GLOBALS.YOUR_NAME_OF_THE_BOT)
        
        elif self._event.message.text == u'抽' or self._event.message.text == 'pick':
            luck_number = random.choice(range(0,100))
            if(luck_number == 87 or not self._inlist):
                self._replyText(MESSAGE.LUCKY_MESSAGE)
            else:
                lst_target_list = self._fb.get_key(GLOBALS.DATABASE_PAGE_RANDOM_PICKED)
                random_picked   = random.choice(list(lst_target_list.keys()))
                if lst_target_list[random_picked]['type'] == 'photo':
                    self._replyImage( lst_target_list[random_picked]['url'] )
        
        elif self._event.message.text == u'ok,bot':
            self._replyText(MESSAGE.WHAT_CAN_I_DO)

        elif self._event.message.text == u'ok,telladmin':
            self._replySenderInfo()

        elif self._event.message.text == u'ok,lang':
            self._set_language()

        else:
            self._echo_bug()

    def _replyImage(self, image_url):
        self._line.reply_message(
                self._event.reply_token,
                ImageSendMessage(
                        original_content_url=image_url,
                        preview_image_url=image_url
                    )
            )

    def _replyText(self, msg):
        self._line.reply_message(
                self._event.reply_token,
                TextSendMessage(
                        text=msg
                    )
            )
    def _echo_bug(self):
        this_msg = self._event.message.text
        dict_msg = { 'type'     : 'yes_man',
                     'key'      :  self._sender_id,
                     'last_msg' : self._event.message.text,
                     'count'    : 0 }
        # Fetch last message from database
        dict_last_msg = self._fb.get_key('yes_man/%s'%self._sender_id)
        # If message change, update message to DB
        # If message is the same, update count
        if dict_last_msg:
            if dict_last_msg['last_msg'] == this_msg:
                dict_last_msg['count'] = dict_last_msg['count'] + 1
                self._fb.update_one(dict_last_msg)
            else:
                self._fb.update_one(dict_msg)
        else:
            self._fb.put_one(dict_msg)
        
        # If count >= 3, reply the same message
        if dict_last_msg and dict_last_msg['count'] >=2 :
            self._replyText(self._event.message.text)
            dict_last_msg['count'] = 0
            self._fb.update_one(dict_last_msg)

    def _replySenderInfo(self, noreply = False):
        user_id   = 'undef'
        user_type = 'undef'
        if self._event.source.type == 'group':
            user_id   = self._event.source.group_id
            user_type = 'group'
        elif self._event.source.type == 'room':
            user_id   = self._event.source.room_id
            user_type = 'room'
        elif self._event.source.type == 'user':
            user_id   = self._event.source.user_id
            user_type = 'user'

        if noreply:
            return user_type, user_id
        else:
            self._replyText('id[%s]\ntype[%s]\nstatus[%s]'%(user_id,user_type,self._inlist))

    def _set_language(self):
        self._line.reply_message(
            self._event.reply_token,
            TemplateSendMessage(
                alt_text='CHANGE LANGUAGE SETTING',
                template=ButtonsTemplate(
                    thumbnail_image_url='https://example.com/image.jpg',
                    title='CHANGE LANGUAGE SETTING',
                    text='Which one do you want?',
                    actions=[
                        PostbackTemplateAction(
                            label=u'我只會說中文',
                            data='action=setlang&value=zh_tw'
                        )
                    ]
                )
            )
        )

class postbackHdlr(requestHdlr):
    def dispatch(self):
        dict_request = parse_qs(self._event.postback.data)
        if 'setlang' in dict_request['action']:
            if 'zh_tw' in dict_request['value']:
                self._replyText(u'中文好，中文妙，中文中文呱呱叫！')
