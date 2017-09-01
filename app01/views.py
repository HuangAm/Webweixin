from django.shortcuts import render,HttpResponse,redirect
import requests
import time
import re
import json

# Create your views here.
def login(req):
    #登录是通过扫二维码登陆的,get访问wx.qq.com,后就应该能看见二维码
    #然后发现二维码是通过img的src加载的,每次刷新登录页面后发现src只有最后一截变
    #说明这个是动态获取的,然后又在network中的请求中看到有一条jslogin开头的url
    #这个url的response获取的uuid和img的src是一样的,然后我们就可以给这个地址发个请求获取
    #uuid然后把获取到的uuid放到前端img的src中进行拼接成完整路径,我们就可以把二维码获取到
    if req.method == 'GET':
        uuid_time = int(time.time()*1000)
        base_uuid_url = "https://login.wx.qq.com/jslogin?appid=wx782c26e4c19acffb&redirect_uri=https%3A%2F%2Fwx.qq.com%2Fcgi-bin%2Fmmwebwx-bin%2Fwebwxnewloginpage&fun=new&lang=zh_CN&_={0}"
        uuid_url = base_uuid_url.format(uuid_time)
        r1 = requests.get(uuid_url)
        result = re.findall('= "(.*)";',r1.text)
        uuid = result[0]
        req.session['UUID_TIME'] = uuid_time
        req.session['UUID'] = uuid
        return render(req,'login.html',{'uuid':uuid})

def ticket(html):
    from bs4 import BeautifulSoup
    ret = {}
    soup = BeautifulSoup(html,'html.parser')
    for tag in soup.find(name='error').find_all():
        ret[tag.name] = tag.text
    return ret

def check_login(req):
    #前端向这里发请求,这里像微信服务器发请求,前端有浏览器同源策略问题
    response = {'code':408,'data':None}
    ctime = int(time.time()*1000)
    base_login_url = "https://login.wx.qq.com/cgi-bin/mmwebwx-bin/login?loginicon=true&uuid={0}&tip=0&r=-765625653&_={1}"
    login_url = base_login_url.format(req.session['UUID'],ctime)
    r1 = requests.get(login_url)
    if 'window.code=408' in r1.text:
        # 无人扫码
        response['code'] = 408
    elif 'window.code=201' in r1.text:
        #扫码成功,返回头像
        response['code'] = 201
        response['data'] = re.findall("window.userAvatar = '(.*)';",r1.text)[0]
    elif 'window.code=200' in r1.text:
        #确认登录
        req.session['LOGIN_COOKIE'] = r1.cookies.get_dict()
        base_redirect_url = re.findall('redirect_uri="(.*)";',r1.text)[0]
        redirect_url = base_redirect_url + '&fun=new&version=v2'

        #获取凭证
        r2 = requests.get(redirect_url)
        print(r2.text)
        ticket_dict = ticket(r2.text)
        req.session['TICKED_DICT'] = ticket_dict
        req.session['TICKED_COOKIE'] = r2.cookies.get_dict()

        #初始化，获取最近联系人信息,公众号
        post_data = {
            "BaseRequest":{
                "DeviceID":"e384757757885382",
                'Sid':ticket_dict['wxsid'],
                'Uin':ticket_dict['wxuin'],
                'Skey':ticket_dict['skey'],
            }
        }

        #用户初始化,将最近联系人个人信息放在session中
        init_url = "https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxinit?r=-740036701&pass_ticket={0}".format(ticket_dict['pass_ticket'])
        r3 = requests.post(
            url=init_url,
            json=post_data
        )
        r3.encoding = 'utf-8'
        init_dict = json.loads(r3.text)
        req.session['INIT_DICT'] = init_dict
        response['code'] = 200
    return HttpResponse(json.dumps(response))

def avatar(req):
    prev = req.GET.get('prev')
    username = req.GET.get('username')
    skey = req.GET.get('key')
    img_url = "https://wx.qq.com{0}&username={1}&skey={2}".format(prev,username,skey)
    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKED_COOKIE'])
    print(img_url)
    res = requests.get(img_url,cookies=cookies,headers={'Content-Type': 'image/jpeg'})
    return HttpResponse(res.content)

def index(req):
    #显示最近联系人
    #http://wx.qq.com
    return render(req,'index.html')

def contact_list(req):
    """
    获取所有联系人
    """
    ctime = int(time.time()*1000)
    base_url = "https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxgetcontact?lang=zh_CN&r={0}&seq=0&skey={1}"
    url = base_url.format(ctime,req.session['TICKED_DICT']['skey'])
    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKED_COOKIE'])
    r1 = requests.get(url,cookies=cookies)
    r1.encoding = 'utf-8'
    user_list = json.loads(r1.text)
    return render(req,'contact_list.html',{'user_list':user_list})

def send_msg(req):
    """
    发送消息
    """
    current_user = req.session['INIT_DICT']['User']['UserName'] #登录后获得唯一标识
    to = req.POST.get('to') #接收者的唯一标识
    msg = req.POST.get('msg')
    #发送消息还需要凭证和Cookie
    ticket_dict = req.session['TICKED_DICT']
    ctime = int(time.time()*1000)
    post_data = {
        "BaseRequest": {
            "DeviceID": "e384757757885382",
            'Sid': ticket_dict['wxsid'],
            'Uin': ticket_dict['wxuin'],
            'Skey': ticket_dict['skey'],
        },
        "Msg": {
            "ClientMsgId": ctime,
            "LocalID": ctime,
            "FromUserName": current_user,
            "ToUserName": to,
            "Content": msg,
            "Type": 1
        },
        "Scene": 0
    }
    url = "https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxsendmsg?pass_ticket={0}".format(ticket_dict['pass_ticket'])
    res = requests.post(url=url,data=json.dumps(post_data,ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json'})
    #ensure_ascii=False是为了能发中文,否则发过去就是Unicode;encode是因为默认是拉丁编码,不支持中文
    print(res.text)
    return HttpResponse('发送成功')

def get_msg(req):
    """
    长轮询获取消息
    """
    #检查是否有消息到来
    ctime = int(time.time()*1000)
    ticket_dict = req.session['TICKED_DICT']
    check_msg_url = "https://webpush.wx.qq.com/cgi-bin/mmwebwx-bin/synccheck"
    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKED_COOKIE'])
    synckey_dict = req.session['INIT_DICT']['SyncKey']
    synckey_list = []
    for item in synckey_dict['List']:
        tmp = "%s_%s" %(item['Key'],item['Val'])
        synckey_list.append(tmp)
    synckey = "|".join(synckey_list)
    r1 = requests.get(
        url=check_msg_url,
        params={
            'r':ctime,
            'deviceid':'e384757757885382',
            'sid':ticket_dict['wxsid'],
            'uin':ticket_dict['wxuin'],
            'skey':ticket_dict['skey'],
            '_':ctime,
            'synckey':synckey
        },
        cookies=cookies
    )
    if '{retcode:"0",selector:"0"}' in r1.text:
        return HttpResponse('...')

    #有消息,获取消息
    base_get_msg_url = "https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxsync?sid={0}&skey={1}&lang=zh_CN&pass_ticket={2}"
    get_msg_url = base_get_msg_url.format(ticket_dict['wxsid'],ticket_dict['skey'],ticket_dict['pass_ticket'])
    post_data = {
        "BaseRequest": {
            "DeviceID": "e384757757885382",
            'Sid': ticket_dict['wxsid'],
            'Uin': ticket_dict['wxuin'],
            'Skey': ticket_dict['skey'],
        },
        'SyncKey': req.session['INIT_DICT']['SyncKey']
    }
    r2 = requests.post(
        url=get_msg_url,
        json=post_data,
        cookies=cookies
    )
    r2.encoding = 'utf-8'
    #接收到消息：消息，synckey
    msg_dict = json.loads(r2.text)
    for msg in msg_dict['AddMsgList']:
        print('您有新的消息：',msg['Content'])
    init_dict = req.session['INIT_DICT']
    init_dict['SyncKey'] = msg_dict['SyncKey']
    req.session['INIT_DICT'] = init_dict
    return HttpResponse('...')

