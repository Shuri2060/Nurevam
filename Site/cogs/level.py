from flask import Blueprint, render_template,request,flash,redirect,url_for,jsonify
import logging
import utils
import math

log = logging.getLogger("Nurevam.site")

blueprint = Blueprint('level', __name__, template_folder='../templates/level',static_folder="static")

name = "levels"
description = "Let your members gain <strong>XP</strong> and <strong> levels</strong> by participating in the chat!"

db = None  #Database


@utils.plugin_page('level')
def dashboard(server_id):
    log.info("Level dashboard")
    key_path = '{}:Level:Config'.format(server_id)
    initial_announcement = '{player}, you just advanced to **level {level}** !\n Now go and fight more mob!'
    announcement = db.hget(key_path,"announce_message")
    if announcement is None:
        db.hset(key_path,"announce_message", initial_announcement)
        db.hset(key_path.format(server_id),"announce",'on')

    cooldown = db.hget(key_path.format(server_id),"rank_cooldown") or 0
    config = db.hgetall(key_path)
    #getting database of members
    db_banned_members = db.smembers('{}:Level:banned_members'.format(server_id)) or []
    db_banned_roles = db.smembers('{}:Level:banned_roles'.format(server_id)) or []
    db_banned_channels = db.smembers('{}:Level:banned_channels'.format(server_id)) or []
    #checking roles
    get_role = utils.resource_get("/guilds/{}".format(server_id))
    guild_roles = get_role['roles']
    #get member info
    get_member = utils.resource_get("/guilds/{}/members?&limit=1000".format(server_id))
    guild_members=[x['user'] for x in get_member]
    #getting channel
    guild_channels = utils.get_channel(server_id)
    #ban role and members
    banned_roles = list(filter(lambda r: r['id'] in db_banned_roles,guild_roles))
    banned_members = list(filter(lambda r:r['id'] in db_banned_members,guild_members))
    banned_channels = list(filter(lambda r:r['id'] in db_banned_channels,guild_channels))
    log.info("Done getting list of banned, now getting rewards roles")
    #reward roles
    role_level = db.hgetall("{}:Level:role_reward".format(server_id)) or {}
    temp = [
        {"name":x['name'],
         "id":x['id'],
         "color":hex(x["color"]).split("0x")[1],
         "level":role_level.get(x["id"],0)} for x in guild_roles]
    temp.sort(key=lambda x: x['name'])

    reward_roles = [temp[:int(len(temp)/2)],temp[int(len(temp)/2):]] #Spliting them into half

    return {
        'config':config,
        'banned_members': banned_members,
        'guild_members':guild_members,
        'banned_roles': banned_roles,
        'guild_roles':guild_roles,
        'banned_channels':banned_channels,
        'guild_channels':guild_channels,
        'cooldown': cooldown,
        "reward_roles":reward_roles,
        }

@blueprint.route('/update/<int:server_id>', methods=['POST'])
@utils.plugin_method
def update_levels(server_id):
    log.info(request.form)
    data = dict(request.form)
    banned_members = data.pop('banned_members')[0].split(',')
    banned_roles = data.pop('banned_roles')[0].split(',')
    banned_channels = data.pop('banned_channels')[0].split(',')
    announcement = data.pop('announcement')[0]
    enable = data.pop('enable',None)
    whisp = data.pop('whisp',None)
    cooldown = data.pop('cooldown',[0])[0]
    data.pop("_csrf_token") #removing it so we can focus on role reward easily
    try:
        cooldown = int(cooldown)
    except ValueError:
        flash('The cooldown that you provided isn\'t an integer!', 'warning')
        return dashboard(server_id=server_id)

    if announcement == '' or len(announcement) > 2000:
        flash('The level up announcement could not be empty or have 2000+ characters.', 'warning')
    else:
        db.hset('{}:Level:Config'.format(server_id),"announce_message", announcement)
        db.hset('{}:Level:Config'.format(server_id),"rank_cooldown", cooldown)

        db.delete('{}:Level:banned_members'.format(server_id))
        if len(banned_members)>0:
            db.sadd('{}:Level:banned_members'.format(server_id), *banned_members)

        db.delete('{}:Level:banned_roles'.format(server_id))
        if len(banned_roles)>0:
            db.sadd('{}:Level:banned_roles'.format(server_id), *banned_roles)

        db.delete('{}:Level:banned_channels'.format(server_id))
        if len(banned_roles)>0:
            db.sadd('{}:Level:banned_channels'.format(server_id), *banned_channels)

        db.hset('{}:Level:Config'.format(server_id),"announce", enable)

        db.hset('{}:Level:Config'.format(server_id),"whisper", whisp)
        role_reward = {}
        for key,values in data.items():
            if "level_role" in key:
                key = key.strip("level_role")
                print(key,values)
                if values[0].isdigit():
                    role_reward[key] = values[0]
                else:
                    flash("Role must be only having integer number!".format(key),"warning")
                    return dashboard(server_id = server_id)
        db.hmset("{}:Level:role_reward".format(server_id),role_reward)
        flash('Settings updated!', 'success')
    log.info("Clear")
    return dashboard(server_id = server_id)

def next_Level(total):
    """
    Formula to get next xp is 100*1.2^level
    It will do calculate level by using log
    then use that level to sub first equations for next level
    This to ensure to make it accurate as it could.
    """
    if int(total) >= 100:  # if it greater than 100, it mean it above level 1
        level = int(math.log(int(total) / 100, 1.2))  # getting level
    else:  # when total exp is less than 100, it is still level 1, reason for that is due to -level via log equations
        level = 1
    next_xp = int(100 * (1.2 ** level))  # getting next require
    return level, next_xp

@blueprint.route('/<int:server_id>')
def levels(server_id):
    is_admin = False
    if utils.session.get('api_token'):
        user_servers = utils.get_user_managed_servers(
            utils.get_user(utils.session['api_token']),
            utils.get_user_guilds(utils.session['api_token']))
        is_admin = str(server_id) in list(map(lambda s:s['id'], user_servers))
    is_private=False
    if db.get("{}:Level:Private".format(server_id)) == "on":
        is_private=True
    #Check if server and plugins_html are in
    server_check = db.hget("Info:Server",server_id)
    if server_check is None:
        return redirect(url_for('index'))
    plugin_check = db.hget("{}:Config:Cogs".format(server_id),"level")
    if plugin_check is None:
        return redirect(url_for('index'))

    log.info("Pass all requirement check")

    server = {
        'id':server_id,
        'name':server_check,
        'icon':db.hget("Info:Server_Icon",server_id)}

    #Players' level
    name_list = db.hgetall("Info:Name")
    avatar_list = db.hgetall("Info:Icon")
    total_member = len(db.smembers("{}:Level:Player".format(server_id)))
    player_data = db.sort("{}:Level:Player".format(server_id), by="{}:Level:Player:*->Total_XP".format(server_id), get=[
                                                                                                          "{}:Level:Player:*->ID".format(server_id),
                                                                                                          "{}:Level:Player:*->XP".format(server_id),
                                                                                                          "{}:Level:Player:*->Total_XP".format(server_id),], start=0, num=total_member, desc=True)
    data = []
    total_exp = 0
    for x in range(0,len(player_data),3):
            if name_list.get(player_data[x+1]) is None:
                db.srem("{}:Level:Player".format(server_id),player_data[x+1])
            if player_data[x] is None: continue
            # print(player_data[x],player_data[x+1]) #for future references
            total_exp += int(player_data[x+2])
            level, next_xp = next_Level(player_data[x+2])
            name = name_list[player_data[x]].split("#")
            temp = {
                "Name":name[0],
                "ID":player_data[x],
                "Level":level,
                "XP":player_data[x+1],
                "Next_XP":next_xp,
                "Total_XP":player_data[x+2],
                "Discriminator":name[1],
                "Avatar":avatar_list.get(player_data[x]),
                "XP_Percent":100*(float(player_data[x+1])/float(next_xp))
            }
            data.append(temp)
    log.info("Done gather player infos")
    #Role rewards
    get_role = utils.resource_get("/guilds/{}".format(server_id))
    guild_roles = get_role['roles']
    role_level = db.hgetall("{}:Level:role_reward".format(server_id)) or {}
    reward_roles = [
        {"name":x['name'],
         "id":x['id'],
         "color":hex(x["color"]).split("0x")[1],
         "level":role_level.get(x["id"],0)} for x in guild_roles if role_level.get(x["id"],"0") != "0" and x["id"] != str(server_id)]
    reward_roles.sort(key=lambda x: x['name'])
    print(reward_roles)
    #Those are for Website
    stats = {"total_member":total_member,"total_exp":total_exp}

    if request.args.get('json'):
        log.info("Requesting Json")
        return jsonify({"server:":server,"reward_roles":reward_roles,"players":data})

    return render_template('level/levels.html', players=data, stats = stats, reward_roles = reward_roles,server=server, title="{} leaderboard".format(server['name']),is_admin=is_admin,is_private=is_private)

@blueprint.route('/server')
def server_levels():
    server_list=db.hgetall("Info:Server")
    server_icon=db.hgetall("Info:Server_Icon")
    enable_level= []
    for server_id in server_list:#run a loops of server list
        if db.hget("{}:Config:Cogs".format(server_id),"level") == "on": #IF this plugins_html is on, then it will collect data
            if db.get("{}:Level:Private".format(server_id)):
                continue
            else:
                player_total=[]
                for player_id in db.smembers("{}:Level:Player".format(server_id)): #Get every player's total XP
                    try:
                        player_total.append(int(db.hget("{}:Level:Player:{}".format(server_id,player_id),"Total_XP")))
                    except:

                        continue
                total = sum(player_total)
                print("{}-{} total xp is {}".format(server_id,server_list[server_id],total))
                try:
                    level = int(math.log(total/100,3))
                except:
                    level = 0
                next_xp = int(100*3**(level+1))
                enable_level.append([server_list[server_id],server_icon.get(server_id),server_id,
                                     total,next_xp,(100*(float(total)/float(next_xp))),level])
    enable_level=sorted(enable_level,key=lambda enable_level:enable_level[4],reverse=True)
    return render_template('level/server_level.html',title="Server Leaderboard",server_list=enable_level)

@blueprint.route('/reset/<int:server_id>/<int:player_id>')
@utils.plugin_method
def reset_player(server_id, player_id):
    log.info("Reset that player's data")
    db.delete('{}:Level:Player:{}'.format(server_id, player_id))
    db.srem('{}:Level:Player'.format(server_id), player_id)
    return redirect(url_for('levels', server_id=server_id))

@blueprint.route('/reset_all/<int:server_id>')
@utils.plugin_method
def reset_all_players(server_id):
    log.info("Someone must be insane reset everything?")
    for player_id in db.smembers('{}:Level:Player'.format(server_id)):
        db.delete('{}:Level:Player:{}'.format(server_id, player_id))
        db.srem('{}:Level:Player'.format(server_id), player_id)
    return redirect(url_for('levels', server_id=server_id))

@blueprint.route('/private_set/<int:server_id>/<int:bool>')
@utils.plugin_method
def private_server(server_id,bool):
    if bool == 1: #set it as private
        db.set("{}:Level:Private".format(server_id),"on")
    else:
        db.delete("{}:Level:Private".format(server_id))
    return redirect(url_for('levels', server_id=server_id))

@blueprint.route('/profile/private_set/<int:player_id>/<int:server_id>/<int:bool>')
@utils.plugin_method
def private_profile(server_id,player_id,bool):
    if bool == 1:
        db.sadd("{}:Level:Player:Private".format(server_id),player_id)
    else:
        db.srem("{}:Level:Player:Private".format(server_id),player_id)
    return redirect(url_for('profile', server_id=server_id,player_id=player_id))

@blueprint.route('/profile/<string:player_id>/<int:server_id>')
def profile_level(player_id,server_id):
    #Checking if is owner of that site
    is_owner = False
    if utils.session.get('api_token'):
        user_id =utils.get_user(utils.session['api_token'])['id']

        is_owner = str(player_id) == str(user_id)
    is_private=player_id in db.smembers("{}:Level:Player:Private".format(server_id))
    server = {
        'id':server_id,
        'name':db.hget("Info:Server",server_id),
        'icon':db.hget("Info:Server_Icon",server_id)
    }
    print(server)
    xp=0
    data_temp = db.hgetall("{}:Total_Command:{}".format(server_id,player_id))
    level_data =db.hgetall("{}:Level:Player:{}".format(server_id,player_id))

    if len(level_data) > 0:
        level, next_exp = next_Level(level_data["Total_XP"])
        level_data.update({"Level":level,"Next_XP":next_exp})
        xp = 100*float(float(level_data["XP"])/float(next_exp))
        level_data.update({"Percents":int(xp)})
        print(level_data)
    else:
        data = None
    #This is command used list
    if len(data_temp) == 0:
        data = None
    else:
        data_array = [(i,data_temp[i])for i in data_temp]
        data_array.sort(key=lambda x: int(x[1]),reverse=True)
        data = ["{} - {}".format(x,y) for x,y in data_array]
    #Their name and icon
    icon = db.hget("Info:Icon",player_id)
    name = db.hget("Info:Name",player_id)
    return render_template("level/profile_level.html",data=data,icon=icon,name=name,player_id=player_id,
                           server=server,level=level_data,XP_Percent=xp,title="{} Profile".format(name),
                            is_owner=is_owner,is_private=is_private)