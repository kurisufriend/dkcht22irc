import requests, websockets, asyncio, json, re, threading, time
from ircked.bot import irc_bot
from ircked.message import *
import traceback

class bird_inst():
    def __init__(self, endpoint, httpendpoint, config):
        self.endpoint = endpoint
        self.httpendpoint = httpendpoint
        self.config = config
        self.ws = None
        self.headers = None
        self.irc = irc_bot(nick=self.config["irc_nick"])
        self.irc.connect_register(self.config["irc_serb"], self.config["irc_port"])
        self.send_queue = []

        def irc_handler(msg, ctx):
            #print("<><><><>", str(msg))
            if msg.command == "PING":
                message.manual("", "PONG", msg.parameters).send(ctx.socket)
            elif msg.command == "001":
                message.manual("", "JOIN", [self.config["irc_chan"]]).send(ctx.socket)
            elif msg.command == "PRIVMSG" and "\x01VERSION\x01" in msg.parameters:
                message.manual(":"+msg.parameters[0], "PRIVMSG", [msg.prefix[1:].split("!")[0], ":\x01dorfl bot\x01"]).send(ctx.socket)
            if msg.command == "PRIVMSG" and ("py-ctcp" not in msg.prefix):
                pm = privmsg.parse(msg)
                self.send_post(pm.fr.split("!")[0]+": "+pm.bod)
        threading.Thread(target=self.irc.run, kwargs={"event_handler": irc_handler}, daemon=True).start()
    def auth(self, name, passwd):
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:83.0) Gecko/20100101 Firefox/83.0",
            "Origin": "https://deekchat.ml", 
            "DNT": "1",
        }
        res = requests.post(self.httpendpoint+"/login/submit", headers=h, data={"name": name, "password": passwd, "submit": "log+in"}, allow_redirects=False)
        token = re.search("(?:api_token)=[^;]+", res.headers.get("Set-Cookie")).group(0)
        sessid = re.search("(?:session_id)=[^;]+", res.headers.get("Set-Cookie")).group(0)
        h["Cookie"] = token+"; "+sessid
        self.headers = h
    async def run(self):
        print("running main loop")
        async with websockets.connect(self.endpoint, extra_headers=self.headers) as self.ws:
            print(self.ws)
            asyncio.get_event_loop().create_task(self._send_post())
            while True:
                data = json.loads(await self.ws.recv())
                print(">>>", data)
                try: getattr(self, "handle_"+data["type"], None)(data)
                except Exception as e: print("hey buddy your shits fucked thought you might want to know", e)
    def handle_message(self, ctx):
        print("btw i just got this", ctx["data"]["message"])
        mesg = ctx["data"]["message"]
        chunks = list(mesg[0+i:500+i] for i in range(0, len(mesg), 500))
        for m in chunks:
            self.irc.sendraw(privmsg.build(self.config["irc_nick"], self.config["irc_chan"], ctx["name"]+": "+m).msg)
    def handle_avatar(self, ctx): pass
    def handle_files(self, ctx):
        self.irc.sendraw(privmsg.build(self.config["irc_nick"], self.config["irc_chan"], ctx["name"]+": "+ctx["data"]["message"]).msg)
        for f in ctx["data"]["files"]:
            self.irc.sendraw(privmsg.build(self.config["irc_nick"], self.config["irc_chan"], f"({ctx['name']} uploaded file: {self.httpendpoint}/storage/files/{f['name']})").msg)
    def handle_exit(self, ctx): pass
    def handle_enter(self, ctx): pass
    def handle_userLoaded(self, ctx): pass
    def send_post(self, msg):
        if self.ws is None: return
        print(msg)
        self.send_queue.append(msg)
    async def _send_post(self):
        while True:
            for msg in self.send_queue:
                await self.ws.send(json.dumps({"type": "message", "data": {"message": msg}}))
                self.send_queue.remove(msg)
                print("shipped", msg)
            await asyncio.sleep(.5)
cfg = json.loads(open("config.json", "r").read())
bi = bird_inst("wss://deekchat.ml/ws", "https://deekchat.ml", cfg)
print("yes hello birdchat here")
bi.auth(cfg["deek_user"], cfg["deek_passwd"])
while True:
    try: asyncio.run(bi.run())
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("yo ur shits broken", e)
        print(traceback.format_exc())
        continue