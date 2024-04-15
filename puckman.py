import discord
import asyncio
import os.path
import random
import json

from discord.ext import commands, tasks
from discord import app_commands
from discord.utils import get

from datetime import timedelta
from dotenv import load_dotenv
from datetime import datetime
from datetime import date
from io import BytesIO
from PIL import Image

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)


try:
    TOKEN = os.environ["TOKEN"]
except KeyError:
    print("no token found in .env")

try:
    STEVEN = os.environ["STEVEN"]
    BERNARDO = os.environ["BERNARDO"]
    GENERAL = os.environ["GENERAL"]
    QUESTIONS = os.environ["BOT_CHANNEL"]
    BOT_TAG = os.environ["BOT_TAG"]
    SCOPES = os.environ["SHEET_SCOPES"]
    HEIGHT_SHEET = os.environ["SHEET_ID"]
except KeyError:
    print("one or multiple environment variables were not found")

RULESJSON = "rules.json"
MOMTXT = "yourmom.txt"
WELCOME = "welcome.txt"
PINGLOG = "ghostpings.txt"
PINGQUEUE = "pings.json"
MESSAGES = "messages.json"
STATSJSON = "stats.json"

HEIGHTS_RANGE = "A2:D"

intents = discord.Intents.all()
intents.message_content = True
intents.guilds = True
intents.members = True


heights = {}
heights_inches = {}
aliases = {}
roles = {}
pings = {}
stats = {}
number_emojis = {
    "0": ":zero:",
    "1": ":one:",
    "2": ":two:",
    "3": ":three:",
    "4": ":four:",
    "5": ":five:",
    "6": ":six:",
    "7": ":seven:",
    "8": ":eight:",
    "9": ":nine:",
}


redundancy_error_messages = []
ping_replies = []


bot = commands.Bot(command_prefix='$', intents=intents, activity=discord.Activity(type=discord.ActivityType.playing, name="hockey"))


#load rule settings from file
with open(RULESJSON, "r", encoding = "utf-8") as rule_file:
    rules = json.load(rule_file)

#load messages that send when a command is used to turn a rule on or off when it already was
with open(MESSAGES, "r", encoding = "utf-8") as messages:
    data = json.load(messages)
    redundancy_error_messages = data["redundancy_error_messages"]
    ping_replies = data["ping_replies"]

#load stats
with open(STATSJSON, "r", encoding = "utf-8") as stats_file:
    stats = json.load(stats_file)


#used to check if a channel is exempt from puckman's wrath
def exempt(channel):
    if not rules["exclude_hw"] or channel != "communal-hw-help-but-steven-uses-it-most":
        return False
    return True

#saves rules to file
def update_rules():
    with open(RULESJSON, "w", encoding = "utf-8") as rule_file:
        json.dump(rules, rule_file)

#saves stats to file
def update_stats():
    with open(STATSJSON, "w", encoding = "utf-8") as stats_file:
        json.dump(stats, stats_file)


#determine how cool a user is
def cool(user):
    score = random.randrange(1,11)
    if user.name == "ashlxywo":
        score = 11
    empty = "⬛"
    if score < 4:
        meter = "🟥"
    elif score < 7:
        meter = "🟨"
    elif score < 10:
        meter = "🟩"
    elif score < 11:
        meter = "🟦"
    else:
        meter = "🟪"
    
    return user.display_name + ", you get a " + str(score) + " on the Puckman Cool Meter™️\n|" + (meter * score) + (empty * (10 - score)) + "|"

#return a message with letters replaced by emoji
def bubble(message):
    content = ""
    for letter in message.strip():
        if letter.isalpha():
            content += (":regional_indicator_" + letter.lower() + ": ")
        elif letter.isnumeric():
            content += (number_emojis[letter] + " ")
        elif letter == " ":
            content += "  "
        else:
            content += letter
    return content




#gets heights of server members from a google spreadsheet
def get_heights():
    global heights
    global heights_inches
    global aliases
        
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
        token.write(creds.to_json())
    
    try:
        service = build("sheets", "v4", credentials=creds)
        
        # Call the Sheets API
        sheet = service.spreadsheets()
        result = (sheet.values().get(spreadsheetId=HEIGHT_SHEET, range=HEIGHTS_RANGE).execute())
        values = result.get("values", [])
    
        if not values:
            print("No data found.")
            return
        
        heights = {}
        heights_inches = {}
        aliases = {}
    
        for row in values:
            if len(row) < 3: continue
        
            heights[row[0]] = row[1]
            

            h_in = None
            try:
                h_in = int(row[2])
            except:
                pass
            
            if h_in != None:
                heights_inches[row[0]] = h_in
            
            if len(row) < 4: continue
            for name in row[3].split(","):
                aliases[name.strip().lower()] = row[0]
    
    except HttpError as err:
        print(err)


def contains(string, parameters):
    string = string.lower()
    for x in parameters:
        if string.find(x) > -1:
            return True
    return False




get_heights()




#ONREADY
@bot.event
async def on_ready():
    global pings
    print("Logged in as {0.user}".format(bot))
    try:
        synced = await bot.tree.sync()
        print("synced {} commands".format(len(synced)))
    except Exception as e:
        print(e)
    
    #attempt to load queue for ghost pings
    with open(PINGQUEUE, "r", encoding = "utf-8") as infile:
        try:
            pings = json.load(infile)
        except:
            pings = {}

    
    check_pings.start() #start loop to check who needs to be pinged

    

#/RULE 
@bot.tree.command(name = "rule", description = "used to view rules with /rule, or change one with /rule [name] [on/off]")
@app_commands.describe(rule = "rule to view or change")
@app_commands.describe(status = "turn rule on or off")
async def rule(ctx, rule:str = "", status:str = ""):
    if rule == "": #display all rules
         await ctx.response.send_message( "Rules:\n\n" + "\n".join( [ (r + ": " + str(rules[r]) + "\n") if ((i + 1) % 5 == 0 and i != 0) else (r + ": " + str(rules[r])) for i, r in enumerate(rules)] ) )
         return

    if rule not in rules:
         await ctx.response.send_message("rule " + rule + " does not exist")
         return

    if status == "": #display status of specified rule
         await ctx.response.send_message("rule {} is currently {}".format(rule, rules[rule]))
         return

    if status.lower() in ["true", "y", "yes", "on", "enable"]:
         if rules[rule]:
             await ctx.response.send_message(random.choice(redundancy_error_messages).format("on"))
             return

         rules[rule] = True
         update_rules()
         await ctx.response.send_message("rule " + rule + " enabled")

    elif str(status).lower() in ["false", "n", "no", "off", "disable"]:
         if not rules[rule]:
             await ctx.response.send_message(random.choice(redundancy_error_messages).format("off"))
             return

         rules[rule] = False
         update_rules()
         await ctx.response.send_message("rule " + rule + " disabled")

    else: #unrecognized status parameter
         await ctx.response.send_message("error: set rule by typing y/n, true/false, or on/off")
         return

@rule.autocomplete("rule")
async def rule_autocomplete(ctx: discord.Interaction, current: str):
    return [app_commands.Choice(name=r, value=r) for r in rules]

@rule.autocomplete("status")
async def status_autocomplete(ctx: discord.Interaction, current: str):
    return [app_commands.Choice(name="on", value="on"), app_commands.Choice(name="off", value="off")]


#/HOWTALL
@bot.tree.command(name = "howtall", description = "tells you how tall people are. pass in a username, display name, or role")
@app_commands.describe(name = "person whose height you want")
async def howtall(ctx: discord.Interaction, name:str):
    stats["/howtalls used"] += 1
    update_stats()

    if name == "":
        await ctx.response.send_message("specify a user or role")
        return
    else:
        if(name not in heights):
             try: #check if name is a display name, rather than a handle
                author = [m for m in ctx.guild.members if str(m.display_name).lower() == name.lower()][0]
             except:
                 old_name = name
                 
                 try: #check if the name passed in was a role
                    name = name[3:name.find(">")]
                    role = [r for r in ctx.guild.roles if str(r.id) == name][0]
                    member_heights = {str(m.display_name) : heights[str(m)].strip() for m in role.members if str(m) in heights}
                    m_heights_inches = {str(m.display_name) : heights_inches[str(m)] for m in role.members if str(m) in heights_inches}
                    content = "heights for " + str(role) + "\n" + "\n".join( [(m + ": " + member_heights[m]) for m in member_heights] )

                    average = sum(m_heights_inches.values()) / len(m_heights_inches.values())

                    content += ("\nAverage for role is {}' {:.2f}\"".format(int(average // 12), average % 12))
                    await ctx.response.send_message(content)
                    return
                 
                 except: #check if name passed in was an alias
                    name = old_name.lower()
                    if (name.lower() in aliases) and (aliases[name.lower()] in heights):
                        await ctx.response.send_message(name + " is " + heights[aliases[name]])
                        return
                    else: #if name couldn't be found anywhere return
                        await ctx.response.send_message ("couldn't find anyone with that name")
                        return

             if str(author) not in heights: #if the name was a display name, check if its corresponding handle is in the dictionary
                await ctx.response.send_message ("I don't know sorry :c")
                return
             else:
                await ctx.response.send_message(author.display_name + " is " + heights[str(author)])

        else: #if the specified name is in the height dictionary
             author = [str(m.display_name) for m in ctx.guild.members if str(m).lower() == name.lower()][0]
             await ctx.response.send_message(author + " is " + heights[name])


# $HOWTALL (old version) - uses $, works by replying to a message
@bot.command()
async def howtall(ctx):
    try:
        message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if str(message.author) not in heights:
                await ctx.reply("I don't know sorry :c")
                return
        else:
            await ctx.reply(str(message.author.display_name) + " is " + heights[str(message.author)])

    except:
        await ctx.reply("reply to someone")
        return

#LOG - logs your mom jokes
@bot.command()
async def log(ctx):
    try:
        message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        td = date.today()

        mom = open(MOMTXT, "a", encoding="utf-8")
        mom.write("\n\n{3}: {0:%B} {0:%d}, {0:%Y} - {1}: {2}".format(td, message.author.display_name, message.content, message.id) )
        mom.close()

        await message.add_reaction("📝")
    except:
        await ctx.reply("reply to someone to log a message")
        return

#DELOG - removes a message from the log
@bot.command()
async def delog(ctx):
    try:
        message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except:
        await ctx.reply("reply to someone to delog a message")
        return

    mom = open(MOMTXT, "r+", encoding="utf-8")
    mom_list = mom.readlines()
    mom.close()
    for i, line in enumerate(mom_list):
        if line.split(":")[0] == str(message.id):
            if i == 0:
                mom_list.pop(i)
                try:
                    mom_list.pop(i)
                except:
                    pass
            elif i == (len(mom_list) - 1):
                mom_list.pop(-1)
                mom_list.pop(-1)
                mom_list[-1] = mom_list[-1].strip()
            else:
                mom_list.pop(i-1)
                mom_list.pop(i-1)

            mom = open(MOMTXT, "w", encoding="utf-8")
            mom.write ("".join([x for x in mom_list]))
            mom.close()
            try:
                await message.remove_reaction("📝", bot.user)
            except:
                pass

            await ctx.reply("message removed from log")
            return
            
    await ctx.reply("couldn't find the requested message")
    return

#DELOG - removes a message by ID
@bot.tree.command(name = "delog", description = "remove a message from the log by ID")
@app_commands.describe(id = "message id")
async def delog_id(ctx, id:str):
    mom = open(MOMTXT, "r+", encoding="utf-8")
    mom_list = mom.readlines()
    mom.close()
    for i, line in enumerate(mom_list):
        if line.split(":")[0] == id:
            if i == 0:
                mom_list.pop(i)
                try:
                    mom_list.pop(i)
                except:
                    pass
            elif i == (len(mom_list) - 1):
                mom_list.pop(-1)
                mom_list.pop(-1)
                mom_list[-1] = mom_list[-1].strip()
            else:
                mom_list.pop(i-1)
                mom_list.pop(i-1)

            mom = open(MOMTXT, "w", encoding="utf-8")
            mom.write ("".join([x for x in mom_list]))
            mom.close()
            await ctx.response.send_message("message removed from log")
            return
            
    await ctx.response.send_message("couldn't find the requested message")
    return
    




#fetches heights from the spreadsheet in case they change after the bot goes online
@bot.tree.command(name = "refresh_heights", description = "updates heights from the saved file")
async def refresh_heights(ctx):
    get_heights()
    await ctx.response.send_message("done")

#uploads the your mom log
@bot.tree.command(name = "print_mom_list", description="print the list of your mom jokes")
async def print_mom_list(ctx):
    await ctx.response.send_message(file=discord.File(r'C:\Users\Zach\Documents\puckman\yourmom.txt'))


#set message to be sent when someone joins the server
@bot.tree.command(name = "set_welcome_message", description = "change the message sent when someone joins the server")
@app_commands.describe(message = "new welcome message")
async def set_welcome_message(ctx, message:str):
    welcome_file = open(WELCOME, "w", encoding = "utf-8")
    welcome_file.write(message)
    welcome_file.close()
    await ctx.response.send_message("updated welcome message")

#display message sent when someone joins
@bot.tree.command(name = "view_welcome_message", description = "see what the welcome message is")
async def view_welcome_message(ctx):
    welcome_file = open(WELCOME, "r", encoding = "utf-8")
    message = welcome_file.read()
    welcome_file.close()
    await ctx.response.send_message(message)

#I steal from Ringo
@bot.tree.command(name = "roulette", description = "try your luck!")
async def roulette(ctx, difficulty:str = ""):
    if difficulty == "standard" or difficulty == "":
        await ctx.response.send_message("💥 " + ctx.user.display_name + " has lost a roulette. 🔫")
    elif difficulty == "casual":
        await ctx.response.send_message("💥 " + ctx.user.display_name + " has lost a casual roulette. 🔫")
    elif difficulty == "maddening":
        await ctx.response.send_message("💥 " + ctx.user.display_name + " has lost a *maddening roulette.* 🔫")
    elif difficulty == "lunatic":
        await ctx.response.send_message("💥 " + ctx.user.display_name + " was foolish enough to believe they could win a **lunatic roulette**. 🔫")
    elif difficulty == "infernal":
        await ctx.response.send_message("💥 " + ctx.user.display_name + " was foolish enough to attempt the INFERNAL ROULETTE and has burned in Hell. 🔥")
    elif difficulty == "stygian":
        await ctx.response.send_message("Darkness has enveloped " + ctx.user.display_name + " in its stygian embrace. It is unknown if they will return.")
    else:
        await ctx.response.send_message("💥 " + ctx.user.display_name + " has lost a roulette. 🔫")
    

@roulette.autocomplete("difficulty")
async def roulette_autocomplete(ctx: discord.Interaction, current: str):
    return [
        app_commands.Choice(name="Standard", value="standard"),
        app_commands.Choice(name="Casual", value="casual"),
        app_commands.Choice(name="Maddening", value="maddening"),
        app_commands.Choice(name="Lunatic", value="lunatic"),
        app_commands.Choice(name="Infernal", value="infernal"),
        app_commands.Choice(name="Stygian", value="stygian")
    ]
    

#ghost ping a random person
@bot.tree.command(name = "random_server_member", description = "annoy someone")
async def random_member(ctx):
    member = random.choice([user for user in ctx.guild.members if not user.bot])
    delay = random.randrange(0, 14400)
    now = datetime.now()
    sendtime = now + timedelta(seconds = delay)
    log = open(PINGLOG, "a", encoding="utf-8")
    log.write(now.strftime("%Y-%m-%d %H:%M:%S") + " - " + ctx.user.display_name + " (" + str(ctx.user.name) + ") ghost pinged " + member.display_name + " (" + str(member.name) + ") with a delay of " + str(delay) + " seconds. They will be pinged at " + sendtime.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    log.close()

    if (sendtime in pings):
        pings[sendtime.strftime("%Y-%m-%d %H:%M:%S")].append(member.id)
    else:
        pings[sendtime.strftime("%Y-%m-%d %H:%M:%S")] = [member.id]

    with open(PINGQUEUE, "w", encoding = "utf-8") as outfile:
        json.dump(pings, outfile)
    await ctx.response.send_message(member.display_name + " will be pinged after " + str(delay) + " seconds. (" + sendtime.strftime("%Y-%m-%d %H:%M:%S") + ")", ephemeral = True)
    

#display stats
@bot.tree.command(name = "stats", description = "show some statistics about how the bot has been used")
async def display_stats(ctx):
    await ctx.response.send_message("\n".join([(key + ": " + str(stats[key])) for key in stats]))

#steal from ringo again
@bot.tree.command(name = "echo", description = "make the bot say something cancellable")
async def echo(ctx:discord.Interaction, message:str, bubbled:bool = False):
    if bubbled:
        msg = bubble(message)
    else:
        msg = message
    msg += ("\n\\- " + ctx.user.display_name)
    await ctx.response.send_message(msg)


#you'll never guess where I got the idea for this command
@bot.tree.context_menu(name = "cool")
async def howcool(ctx: discord.Interaction, user: discord.User):
    await ctx.response.send_message(cool(user))

#send someone's profile picture with some added decorations
@bot.tree.context_menu(name = "clown")
async def clown(ctx: discord.Interaction, user: discord.User):
    pfp = await user.avatar.read()
    pfp = Image.open(BytesIO(pfp))
    pfp = pfp.resize((384, 384))
    clown = Image.open(r"C:\Users\Zach\Documents\puckman\clown.png").convert("RGBA")
    pfp.paste(clown, (0,0), clown)
    with BytesIO() as output:
        pfp.save(output, "PNG")
        output.seek(0)
        await ctx.response.send_message(file=discord.File(fp=output, filename="pfp.png"))

#sends a message to the #Bernardo-questions channel. Requested by Steven
@bot.tree.context_menu(name = "log_question")
async def log_question(ctx: discord.Interaction, message: discord.Message):
    channel = bot.get_channel(QUESTIONS)
    await channel.send("\"" + message.content + "\"")
    await ctx.response.send_message("message sent to " + channel.mention, ephemeral = True)

#checks for anyone that needs to get ghost pinged every 5 seconds
@tasks.loop(seconds = 5)
async def check_pings():
    channel = bot.get_channel(GENERAL)
    now = datetime.now()
    delete = []
    for sendtime in pings:
        timeobj = datetime.strptime(sendtime, "%Y-%m-%d %H:%M:%S")
        if now >= timeobj:
            for user in pings[sendtime]:
                member = bot.get_user(user)
                await channel.send(member.mention, delete_after=1)
                log = open(PINGLOG, "a", encoding = "utf-8")
                log.write(now.strftime("%Y-%m-%d %H:%M:%S") + " - JUST PINGED: " + str(member.display_name) + " (" + str(member.name) + ")\n")
                log.close()

                stats["ghost pings"] += 1
                update_stats()

            delete.append(sendtime)
    
    for sendtime in delete:
        del pings[sendtime]
        with open(PINGQUEUE, "w", encoding = "utf-8") as outfile:
            json.dump(pings, outfile)
    

#sync commands
@bot.command()
async def sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.channel.send("synced {} commands".format(len(synced)))
    except Exception as e:
        await ctx.channel.send(e)


#triggers every time a message is sent
@bot.event
async def on_message(message):
    global roles
    
    if message.author == bot.user: #skip the bot's messages
         return

    if rules["letter_roles"] and not message.content.startswith("$"): #if letter roles are enabled, replace letters with their roles
         if len([char for char in list(message.content) if char.isalpha()]) == 0:
             return
         if message.content.startswith("https://"):
             return
         
         if not roles:
             roles = { role.name: role for role in message.guild.roles if len(role.name) == 1 }

         new_content = ["<@&{}>".format(roles[x.upper()].id) if x.upper() in roles \
                                          else x for x in list(message.content)]
         
         for i, x in enumerate(new_content):
             if x == " ":
                  new_content[i] = "      "

         new_content = "".join(new_content)

         await message.delete()

         await message.channel.send(str(message.author.display_name) + ": ")
         index = 0
         while len(new_content) > 0:
             if len(new_content) < 2000:
                  await message.channel.send(new_content)
                  break
             
             cutoff = new_content.find("<", min(1950, len(new_content)))
             await message.channel.send(new_content[index:cutoff])
             new_content = new_content[cutoff:]
    
    if rules["steven_mom"] and not message.content.startswith("$") and \
   message.content.lower().find("ur mom") > -1 and str(message.author) == STEVEN: #make fun of Steven's your mom jokes
             await message.reply("bottom tier")
    
    if rules["log_mom_jokes"] and (contains(message.content, ["ur mom", "tu madre", "ur mother"])): #log mom jokes
        td = date.today()

        mom = open(MOMTXT, "a", encoding="utf-8")
        mom.write("\n\n{3}: {0:%B} {0:%d}, {0:%Y} - {1}: {2}".format(td, message.author.display_name, message.content, message.id) )
        mom.close()

        stats["mom jokes logged"] += 1
        update_stats()

        await message.add_reaction("📝")
    
    if rules["harass_steven"] and str(message.author) == STEVEN: #react to all of steven's messages
        emoji = get(bot.emojis, name="JPMAboutToSayUrStupid")   
        await message.add_reaction(emoji)
    
    if rules["delete_steven"] and str(message.author) == STEVEN and not exempt(str(message.channel)): #20% chance of deleting steven's messages
         if random.randrange(1, 6) == 5:
              await asyncio.sleep(3)
              await message.delete()
              await message.channel.send("Puckman has deleted this message. Have a nice day!")
              await bot.get_channel(QUESTIONS).send(str(message.author.display_name) + ": " + str(message.content))
    
    if rules["delete_bernardo"] and str(message.author) == BERNARDO and not exempt(str(message.channel)): #20% chance of deleting bernardo's messages
         if random.randrange(1, 6) == 5:
              await asyncio.sleep(3)
              await message.delete()
              await message.channel.send("Puckman has deleted this message. Have a nice day!")
              await bot.get_channel(QUESTIONS).send(str(message.author.display_name) + ": " + str(message.content))
    
    if rules["puckin_time"] and message.content.lower().find("time") > -1: #respond to any message containing "time"
        await message.reply("It's puckin' time!")

    if rules["reply_to_pings"] and message.content.find(BOT_TAG) > -1: #respond to any message that pings puckman
        await message.reply(random.choice(ping_replies))
    
    await bot.process_commands(message)

#on server join, ping them with the welcome message
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(GENERAL)
    welcome_file = open(WELCOME, "r", encoding = "utf-8")
    welcome = welcome_file.read()
    welcome_file.close()
    await channel.send((member.mention) + " " + welcome)




#run :>
bot.run(TOKEN)