from discord.ext import commands
from .utils import utils
import traceback
import datetime
import asyncio
import aiohttp
import discord
import logging
import html

log = logging.getLogger(__name__)

def html_unscape(term):
    return html.unescape(term)

class Discourse(): #Discourse, a forums types.
    def __init__(self,bot):
        self.bot = bot
        self.redis = bot.db.redis
        self.counter= 0
        self.log_error = {}
        loop = asyncio.get_event_loop()
        self.loop_discourse_timer = loop.create_task(self.timer())

    def __unload(self):
        self.loop_discourse_timer.cancel()
        utils.prLightPurple("Unloading Discourse")

    def __local_check(self,ctx):
        return utils.is_enable(ctx,"discourse")

    def logging_info(self,status,link,thread_id,guild_id):
        if isinstance(status,int):
            if status == 404:
                status = "Not found."
            elif status == 410:
                status = "Missing."
            elif status == 403:
                status = "Cannot access it."
            else:
                status = "???"
        elif bool(status) is True:
            status = "Working."
        elif bool(status) is False:
            status = "Cannot connect."
        else:
            status = "???"
        self.log_error[guild_id] = {"status":status,"link":link,"id":thread_id,"time":datetime.datetime.now()}

    async def get_data(self,link,api,username,domain,guild=None):
        #Using headers so it can support both http/1 and http/2
        #Two replace, one with https and one with http...
        # utils.prCyan("Under get_data, {}".format(link))
        try:
            headers = {"Host": domain.replace("http://","").replace("https://","")}
            link = "{}.json?api_key={}&api_username={}".format(link,api,username)
            with aiohttp.ClientSession() as discourse:
                async with discourse.get(link,headers=headers) as resp:
                    log.debug(resp.status)
                    if resp.status == 200:
                        return True,await resp.json()
                    else:
                        return False,resp.status
        except asyncio.CancelledError: #Just in case here for some reason
            utils.prRed("Under get_data function")
            utils.prRed("Asyncio Cancelled Error")
            return False,None
        except:
            utils.prRed("Under get_data function, server: {}".format(guild))
            utils.prRed(traceback.format_exc())
            return False,None

    async def new_post(self,guild_id):
        log.debug(guild_id)
        if await self.redis.hget('{}:Config:Cogs'.format(guild_id),"discourse") is None:
            return log.debug("Disable")

        config = await self.redis.hgetall("{}:Discourse:Config".format(guild_id))
        log.debug(config) #checking to see if there is config in
        if not (config):
            return
        id_post = await self.redis.get("{}:Discourse:ID".format(guild_id))
        log.debug(id_post)
        if not(id_post):
            log.debug("ID post is missing")
            return
        id_post = int(id_post)
        counter = 0
        error_404 = 0
        data = {}
        status,link,get_post = "???"
        while True:
            log.debug("Counter is {}".format(counter))
            self.logging_info(get_post, link, id_post + counter, guild_id)
            counter += 1
            link = "{}/t/{}".format(config['domain'],id_post+counter)
            status,get_post = await self.get_data(link, config['api_key'], config['username'], config['domain'],guild_id)
            if status is False:
                if get_post in (404,410):
                    counter -= 1
                elif get_post == 403:
                    error_404 += 1
                    if error_404 >= 10:
                        await self.redis.set("{}:Discourse:ID".format(guild_id), id_post + counter)
                        break
                    continue
                break
            elif status is True:
                log.debug("It have post")
                if get_post["archetype"] == "regular":
                    check_exist = data.get(get_post["category_id"])
                    if check_exist is None:
                        data[get_post["category_id"]] = []
                    data[get_post["category_id"]].append("{2}\t\tAuthor: {0[details][created_by][username]}\n{1}".format(get_post,link,html_unscape(get_post["fancy_title"])))
        if data:
            log.debug("Got a data to post to channel")
            raw_channel = await self.redis.hgetall("{}:Discourse:Category".format(guild_id))
            for key,values in data.items():
                log.debug("{} and {}".format(key,values))
                channel = config["channel"]
                for x in raw_channel:
                    if str(key) in x:
                        channel = raw_channel[x]
                if channel == "0":
                    channel = config["channel"]
                channel_send = self.bot.get_channel(int(channel))
                if channel_send is None:
                    log.debug("Channel is not found, {}".format(channel))
                    continue
                await channel_send.send("\n".join(values))
                utils.prLightPurple("\n".join(values))
            await self.redis.set("{}:Discourse:ID".format(guild_id),id_post+counter)

    async def timer(self):
        self.bot.id_discourse += 1
        id_count = self.bot.id_discourse #testing ID of loops, how many time is there that
        utils.prPurple("Starting Discourse Loops time")
        counter_loops = 0
        while True:
            try:
                log.debug("Back to start loops {}".format(counter_loops))
                if counter_loops == 30:
                    self.counter += 1
                    utils.prPurple("Discourse Loops check! {}-ID:{}".format(self.counter,id_count))
                    counter_loops = 0
                if self.bot.id_discourse != id_count:  # if it don't match, it will return
                    return utils.prRed("{} does not match within ID of {}! Ending this loops now".format(self.bot.id_discourse,id_count))
                self.bot.background.update({"discourse":datetime.datetime.now()})
                for guild in list(self.bot.guilds):
                    await self.new_post(guild.id)
                counter_loops += 1
                log.debug("Sleeping...")
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                return utils.prRed("Asyncio Cancelled Error")
            except Exception as e:
                print(e)
                utils.prRed(traceback.format_exc())


#########################################################################
#     _____                                                       _     #
#    / ____|                                                     | |    #
#   | |        ___    _ __ ___    _ __ ___     __ _   _ __     __| |    #
#   | |       / _ \  | '_ ` _ \  | '_ ` _ \   / _` | | '_ \   / _` |    #
#   | |____  | (_) | | | | | | | | | | | | | | (_| | | | | | | (_| |    #
#    \_____|  \___/  |_| |_| |_| |_| |_| |_|  \__,_| |_| |_|  \__,_|    #
#                                                                       #
#########################################################################

    @commands.command(name="summary",brief="Showing a summary of user")
    async def summary_stat(self,ctx,*,name: str): #Showing a summary stats of User
        '''
        Give a stat of summary of that username
        Topics Created:
        Posts Created:
        Likes Given:
        Likes Received:
        Days Visited:
        Posts Read:
        '''
        config =await self.redis.hgetall("{}:Discourse:Config".format(ctx.message.guild.id))
        link ="{}/users/{}/summary".format(config["domain"],name)
        data = await self.get_data(link,config["api_key"],config['username'],config["domain"])  #Get info of that users
        utils.prGreen(data)
        data = data[1]
        if data == 404: #If there is error  which can be wrong user
            await self.bot.say(ctx,"{} is not found! Please double check case and spelling!".format(name))
            return
        summary=data["user_summary"] #Dict short for print_data format
        print_data= "Topics Created:{0[topic_count]}\n" \
                    "Post Created:{0[post_count]}\n" \
                    "Likes Given:{0[likes_given]}\n" \
                    "Likes Received:{0[likes_received]}\n" \
                    "Days Visited:{0[days_visited]}\n" \
                    "Posts Read:{0[posts_read_count]}".format(summary)
        await self.bot.say(ctx,"```xl\n{}\n```".format(print_data))

    @commands.command(name="stats",brief="Show a Site Statistics")
    async def statistics(self,ctx): #To show a stats of website of what have been total post, last 7 days, etc etc
        '''
        Show a table of Topics,Posts, New Users, Active Users, Likes for All Time, Last 7 Days and Lasts 30 Days
        '''
        config =await self.redis.hgetall("{}:Discourse:Config".format(ctx.message.guild.id))
        data=await self.get_data("{}/about".format(config["domain"]),config["api_key"],config["username"],config["domain"]) #Read files from link Main page/about
        data = data[1]
        stat=data["about"]["stats"]
        await self.bot.say(ctx,"```xl"
                           "\n┌──────────────┬──────────┬──────────────┬──────────────┐\n"
                           "│              │ All Time │ Lasts 7 Days │ Last 30 Days │"
                           "\n├──────────────┼──────────┼──────────────┼──────────────┤"
                           "\n│ Topics       │{0:^10}│{1:^14}│{2:^14}│"
                           "\n├──────────────┼──────────┼──────────────┼──────────────┤"
                           "\n│ Posts        │{3:^10}│{4:^14}│{5:^14}│"
                           "\n├──────────────┼──────────┼──────────────┼──────────────┤"
                           "\n│ New Users    │{6:^10}│{7:^14}│{8:^14}│"
                           "\n├──────────────┼──────────┼──────────────┼──────────────┤"
                           "\n│ Active Users │    —     │{9:^14}│{10:^14}│"
                           "\n├──────────────┼──────────┼──────────────┼──────────────┤"
                           "\n│ Likes        │{11:^10}│{12:^14}│{13:^14}│"
                           "\n└──────────────┴──────────┴──────────────┴──────────────┘\n```".format(
                   stat["topic_count"],stat["topics_7_days"],stat["topics_30_days"],
                   stat["post_count"],stat["posts_7_days"],stat["posts_30_days"],
                   stat["user_count"],stat["users_7_days"],stat["users_30_days"],
                   stat["active_users_7_days"],stat["active_users_30_days"],
                   stat["like_count"],stat["likes_7_days"],stat["likes_30_days"]))

    @commands.command(brief="Give a bio of that user")
    async def bio(self,ctx,name:str):
        """
        Give a info of Username
        Username:
        Total Badge:
        View:
        Join:
            Date:
            Time:
        Bio:
        """
        if " " in name:
            await self.bot.say("There is space in! There is no such name that have space in! Please Try again!")
            return
        config =await self.redis.hgetall("{}:Discourse:Config".format(ctx.message.guild.id))
        read= await self.get_data("{}/users/{}".format(config["domain"],name),config["api_key"],config["username"],config["domain"])
        if read[1] == 404: #If there is error  which can be wrong user
            await self.bot.say("{} is not found! Please double check case and spelling!".format(name))
            return
        read= read[1]
        data =read["user"]
        data_array=[]
        data_array.append("**Username**: {}".format(data["username"]))
        if data.get("name","") != "":
            data_array.append("**Name**: {}".format(data["name"]))
        if data.get("title",None) != None:
            data_array.append("**Title**: {}".format(data['title']))
        data_array.append("**Total Badge**: {}".format(data["badge_count"]))
        data_array.append("**View**: {}".format(data["profile_view_count"]))
        data_array.append("**Join**:\n\tDate:{}".format(data["created_at"][:-5].strip().replace("T", " \n\tTime:")))
        if "bio_raw" in data:
            data_array.append("**Bio**: \n```\n{}\n```".format(data["bio_raw"]))
        await self.bot.say(ctx,"\n".join(data_array))

    @commands.command(brief="show Logging of discourse",hidden = True)
    async def dstatus(self,ctx):
        """
        Allow to display a log for this guild, Give you a update current ID.
        """
        data = self.log_error.get(ctx.message.guild.id)
        if data is None:
            await self.bot.say_edit("I cannot check it at this moment!")
        else:
            embed = discord.Embed()
            embed.add_field(name = "Status", value=data["status"])
            embed.add_field(name = "ID", value = "[{0[id]}]({0[link]})".format(data))
            embed.timestamp = data["time"]
            await self.bot.say(ctx,embed=embed)

def setup(bot):
    bot.add_cog(Discourse(bot))
