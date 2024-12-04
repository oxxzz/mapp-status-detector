''' Detect wechat app status
    File: wechat.py

    Deps:
        uv: curl -LsSf https://astral.sh/uv/install.sh | sh
        selenium:
        ```docker run -d -p 4444:4444 -p 7900:7900 --shm-size="2g" --name selenium -e SE_VNC_PASSWORD=secret selenium/standalone-chrome:latest ```

    CfgFile: cfg.yaml
    ```yaml
    debug: false
    chrome-remote: http://127.0.0.1:4444/wd/hub # selenium remote address
    app:
        blacklist: []
        detect-api: https://mp.weixin.qq.com/mp/waerrpage?appid={}&type=offshelf&offshelf_type=0&devicetype=iOS16.3.1&version=18002126&lang=zh_CN&nettype=WIFI&ascene=0&fontScale=100&pass_ticket=ogxNSFslKeiFlmat1WVJRa/LB9UA4qKn+7lNRdWcqe5GMF9tN3MvkopFniR3X19xlDn4sO/ECPkO6CmHeslDfA==&wx_header=3

    db:
        mysql:
            host: xxxxx.polarx.rds.aliyuncs.com
            port: 3306
            database: db
            username: user
            password: secret
    ```

    Run:
        uv run wechat.py >> logs/wechat.log
'''

from bs4 import BeautifulSoup
from selenium import webdriver
import yaml, sys, os, pymysql, requests, logging

# set logging output to stdout
logging.basicConfig(
    filemode="a",
    filename="logs/wechat.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

cfgFile = os.path.abspath(os.path.dirname(__file__)) + "/cfg.yaml"

try:
    with open(cfgFile, "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        logging.info("load config file: {}".format(cfgFile))
except Exception as e:
    logging.error(e)
    sys.exit(1)

db = pymysql.connect(
    host=config['db']['mysql']['host'] or '127.0.0.1',
    port=config['db']['mysql']['port'] or 3306,
    user=config['db']['mysql']['username'] or '',
    password=config['db']['mysql']['password'] or '',
    database=config['db']['mysql']['database'] or 'mysql',
    charset='utf8',
    connect_timeout=5
)

if not db.open:
    logging.error("mysql connect error")
    sys.exit(1)

api = config['app']['detect-api'] or ''
if api == '':
    logging.error("app detect api is empty")
    sys.exit(1)

blacklist = config['app']['blacklist'] or []
tokens = (
    '封禁',
    '永久',
    '违规',
    '违反',
    '暂停服务',
    '故障',
    '涉嫌',
    '涉及',
    '不符',
)

options = webdriver.ChromeOptions()
options.add_argument('--blink-settings=imagesEnabled=false')

if not config.get('debug'):
    options.add_argument('--headless')

chrome = webdriver.Remote(config.get('chrome-remote', 'http://127.0.0.1:4444/wd/hub'), options=options)
dingApi = 'https://oapi.dingtalk.com/robot/send?access_token=4483200e0d60953eca042e96d3a7466cd6f4a99e6053a6634122c4066ad7b907'

# send ding web hook message
def dingMessage(appName, appId, title, description, platform = '微信'):
    try:
        headers = {
            'Content-Type': 'application/json',
        }
        data = {
            "msgtype": "text",
            "text": {
                "content": f"[DT] {platform}小程序: {appName} ({appId}) | {title},{description}"
            },
            "at": {
                "isAtAll": True
            }
        }
        resp = requests.post(dingApi, headers=headers, json=data)
        logging.info("send ding message response: {}".format(resp.text))
    except Exception as e:
        logging.error(e)

try:
    cur = db.cursor()
    cur.execute('select uuid, name from mapps where platform_type = 2 and status = 1')
    for row in cur.fetchall():
        if not (row[0] or '').startswith('wx'):
            logging.warning("name: {} invalid app id {}".format(row[1], row[0]))
            continue

        if blacklist and row[0] in blacklist:
            logging.warning("app: {} {} in blacklist".format(row[1], row[0]))
            continue

        chrome.get(api.format(row[0]))
        soup = BeautifulSoup(chrome.page_source, 'html.parser')
        tdom = soup.find('h2', class_='weui-msg__title')
        ddom = soup.find('p', class_='weui-msg__desc')
        title = tdom.text.strip() if tdom is not None else ''
        description = ddom.text.strip() if ddom is not None else ''

        logging.info("detect app: {} {} {} {}".format(row[1], row[0], title, description))
        if not title or not any(x in title for x in tokens):
            continue
        dingMessage(row[1], row[0], title, description)
    cur.close()
except Exception as e:
    logging.error(e)

chrome.quit()
db.close()
sys.exit(0)