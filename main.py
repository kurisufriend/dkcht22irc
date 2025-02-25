import requests, websockets, asyncio, json, re, threading, time
from ircked.bot import irc_bot
from ircked.message import *
import traceback
import html
import ratelimiter

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

        self.limiter = ratelimiter.ratelimit(.5)

        def irc_handler(msg, ctx):
            if msg.command == "PING":
                message.manual("", "PONG", msg.parameters).send(ctx.socket)
            elif msg.command == "001":
                for chan in self.config["irc_chan2deekroomid"].keys():
                    message.manual("", "JOIN", [chan]).send(ctx.socket)
            elif msg.command == "PRIVMSG" and "\x01VERSION\x01" in msg.parameters:
                message.manual(":"+msg.parameters[0], "PRIVMSG", [msg.prefix[1:].split("!")[0], ":\x01dorfl bot\x01"]).send(ctx.socket)
            if msg.command == "PRIVMSG" and ("py-ctcp" not in msg.prefix):
                pm = privmsg.parse(msg)
                post = pm.bod
                if pm.fr.split("!")[0] != self.config["passthru_nick"]: post = "<"+pm.fr.split("!")[0]+"> " + post
                self.send_post(post, self.config["irc_chan2deekroomid"][pm.to])
        threading.Thread(target=self.irc.run, kwargs={"event_handler": irc_handler}, daemon=True).start()
    def auth(self, name, passwd):
        h = {
            "User-Agent": "renabot",
            "Origin": "https://deek.chat", 
            "DNT": "1",
        }
        res = requests.post(self.httpendpoint+"/login/submit", headers=h, data={"name": name, "password": passwd, "submit": "log+in"}, allow_redirects=False)
        print(res.headers)
        token = re.search("(?:api_token)=[^;]+", res.headers.get("Set-Cookie")).group(0)
        sessid = re.search("(?:session_id)=[^;]+", res.headers.get("Set-Cookie")).group(0)
        h["Cookie"] = token+"; "+sessid
        self.headers = h
    async def run(self):
        print("running main loop")
        async with websockets.connect(self.endpoint, extra_headers=self.headers) as self.ws:
            print(self.ws)
            asyncio.get_event_loop().create_task(self._send_post())
            asyncio.get_event_loop().create_task(self.ship_queued_messages())
            while True:
                data = json.loads(await self.ws.recv())
                print(">>>", data)
                #getattr(self, "handle_"+data["type"], None)(data)
                try: getattr(self, "handle_"+data["type"], None)(data)
                except Exception as e: print("hey buddy your shits fucked thought you might want to know", e)
    def handle_message(self, ctx):
        room = int(ctx["roomId"])
        if not room in self.config["irc_chan2deekroomid"].values(): return
        print("btw i just got this", ctx["data"]["text"])
        ctx["data"]["text"] = html.unescape(ctx["data"]["text"])
        if ctx["data"]["name"] == self.config["deek_user"]: return
        mesg = ctx["data"]["text"].replace("\n", " ")
        chunks = list(mesg[0+i:400+i] for i in range(0, len(mesg), 400))
        chunks = ["<"+ctx["data"]["name"]+"> "+m for m in chunks]
        chunks[0] = f"(#{ctx['data']['id']}) " + chunks[0]
        irc_chan = ""
        for k in self.config["irc_chan2deekroomid"].keys():
            if self.config["irc_chan2deekroomid"][k] == room:
                irc_chan = k
        for m in chunks:
            self.limiter.action(True, self.irc.sendraw, (privmsg.build(self.config["irc_nick"], irc_chan, m).msg,))
    def handle_messageStart(self, ctx): pass
    def handle_messageChange(self, ctx): pass
    def handle_messageEnd(self, ctx): self.handle_message(ctx)
    def handle_avatar(self, ctx): pass
    def handle_loadUsers(self, ctx): pass
    def handle_files(self, ctx):
        room = int(ctx["roomId"])
        if not room in self.config["irc_chan2deekroomid"].values(): return
        ctx["data"]["text"] = html.unescape(ctx["data"]["text"])
        irc_chan = ""
        for k in self.config["irc_chan2deekroomid"].keys():
            if self.config["irc_chan2deekroomid"][k] == room:
                irc_chan = k
        self.irc.sendraw(privmsg.build(self.config["irc_nick"], irc_chan, "<"+ctx["data"]["name"]+"> "+ctx["data"]["text"]).msg)
        for f in ctx["data"]["files"]:
            self.limiter.action(True, self.irc.sendraw, (privmsg.build(self.config["irc_nick"], irc_chan, f"({ctx['data']['name']} uploaded file: {self.httpendpoint}/storage/files/{f['name']} )").msg,))
    def handle_exit(self, ctx): pass
    def handle_enter(self, ctx): pass
    def handle_userLoaded(self, ctx): pass
    def send_post(self, msg, room):
        if self.ws is None: return
        print(msg)
        self.send_queue.append((msg, room))
    async def _send_post(self):
        while True:
            for msg in self.send_queue:
                await self.ws.send(json.dumps({"type": "message", "data": msg[0], "roomId": msg[1]}))
                self.send_queue.remove(msg)
                print("shipped", msg)
            await asyncio.sleep(.1)
    async def ship_queued_messages(self):
        while True:
            self.limiter.lazyrun()
            await asyncio.sleep(.1)
cfg = json.loads(open("config.json", "r").read())
bi = bird_inst("wss://deek.chat/ws", "https://deek.chat", cfg)
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
