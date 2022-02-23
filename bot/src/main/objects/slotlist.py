import discord
import mysql.connector
from discord import utils as dutils
from math import ceil
from datetime import datetime, timedelta

from bot.config.loader import cfg
from bot.src.main.objects.util import Util, with_cursor


def get_line_data(line: str, last: int, manuel: bool = False) -> (int, dict):
    """
    Extracts information from a line of a slotlist
    Args:
        line: line of a slotlist
        last: last slot number
        manuel: disables automatic slotnumber generation

    Returns:
       int(num), {num: {"User": playername, "Description": description}}

    """
    output = {"Description": "", "User": ""}
    num = ""
    line = line.replace("**", "").split("-")

    output["User"] = "-".join(line[1:]).replace("**", "")
    line = line[0]

    for x in line[1:]:
        if x.isdigit():
            num += x
        else:
            break

    if not manuel and int(num) == 0:  # If slotnumber is 0, then autofit slotnumber
        num = str(last + 1).zfill(len(num))

    output["Description"] = line[len(num) + 1:].strip()

    output["User"] = output["User"].strip()

    return int(num), {num: output}


def get_members(name: str, channel: discord.TextChannel) -> discord.Member:
    """
    Gets a member of a list
    Args:
        name: Name of a user
        channel: Discord text channel

    Returns: Discord Member

    """

    result = dutils.find(lambda x: x.name == name or x.nick == name, channel.guild.members)
    if result:
        return result
    else:   # If user has as mark try to find without mark
        name = name.split("<:")[0].strip()
        result = dutils.find(lambda x: x.name == name or x.nick == name, channel.guild.members)
        return result


class IO:
    def __init__(self, cfg, db, util: Util):
        self.cfg = cfg
        self.db = db

        self.util = util

    @with_cursor
    def get_user_id(self, cursor: mysql.connector.MySQLConnection.cursor,
                    nname: str, channel: discord.TextChannel) -> str:
        """
        Gets an user id
        Args:
            cursor: Database cursor
            nname: Nickname of a user
            channel: Channel

        Returns: Discord Member ID
        """

        sql = "SElECT ID FROM User WHERE Nickname = %s;"
        cursor.execute(sql, [nname])
        result = cursor.fetchall()

        if result:
            return result[0][0]
        else:
            nname = get_members(nname, channel)

            if not nname:
                return None

            sql = f"INSERT IGNORE INTO User (ID, Nickname) VALUES (%s, %s);"
            var = [nname.id, nname.display_name]
            cursor.execute(sql, var)
            self.db.commit()

            return str(nname.id)

    @with_cursor
    def pull_reserve(self, cursor: mysql.connector.MySQLConnection.cursor, event_id: int) -> bool:
        """
        Pulls users from reserve into open slots
        Args:
            cursor: Database cursor
            event_id: Event ID

        Returns:
            (bool): if free slots exist
        """

        sql = "SELECT Number FROM Slot " \
              "WHERE Event = %s AND User IS NULL AND Description != 'Reserve';"

        cursor.execute(sql, [event_id])
        free = cursor.fetchall()

        sql = "SELECT Number, User FROM Slot " \
              "WHERE Event = %s and User IS NOT NULL AND Description = 'Reserve' " \
              "ORDER BY CONVERT(Number, UNSIGNED INTEGER);"

        cursor.execute(sql, [event_id])
        reserve = cursor.fetchall()

        if free and reserve:
            for index, elem in enumerate(free, start=0):

                if index == len(reserve):
                    return True

                sql = "UPDATE Slot SET User= NULL WHERE Event= %s and Number = %s;"
                var = [event_id, reserve[index][0]]
                cursor.execute(sql, var)
                self.db.commit()

                sql = "UPDATE Slot SET User= %s WHERE Event= %s and Number = %s;"
                var = [reserve[index][1], event_id, elem[0]]
                cursor.execute(sql, var)
                self.db.commit()

            return False
        elif free:
            return True
        else:
            return False

    @with_cursor
    def sort_reserve(self, cursor: mysql.connector.MySQLConnection.cursor, channel: discord.TextChannel) -> None:
        """
        Sorts the reserve slots, so its filled from bottom up
        Args:
            cursor:  Database cursor
            channel: Server channel
        """

        sql = "SELECT Number, User FROM Slot WHERE Event = %s and Description = 'Reserve' ORDER BY Number"
        cursor.execute(sql, [channel.id])
        reserve = cursor.fetchall()

        count = 0

        for x, y in reserve:
            if not y:
                continue
            else:
                sql = "UPDATE Slot SET User = NULL WHERE User = %s AND Event = %s;"
                cursor.execute(sql, [y, channel.id])
                self.db.commit()

                sql = "UPDATE Slot SET User = %s WHERE Number = %s AND Event = %s;"
                var = [y, reserve[count][0], channel.id]
                cursor.execute(sql, var)
                self.db.commit()

                count += 1

    @with_cursor
    def create(self, cursor: mysql.connector.MySQLConnection.cursor, msg_list: [discord.Message],
               author: discord.Member, time: str, bot: discord.User = None, manuel: bool = False) -> bool:
        """
        Creates an event in the database
        Args:
           cursor: Database cursor
           msg_list: The message containing the slotlist
           author: Author of the slotlist
           time: start time of the event
           bot: Used Bot user (optional)
           manuel: if slot-generation should be manuel

        Returns:
           (bool): if successful
        """

        channel = msg_list[0].channel
        split = channel.name.split("-")
        time = time[:2] + ':' + time[2:] + ":00"

        if not (len(split) == 4 and len(split[0]) == 4 and len(split[1]) == 2 and len(split[2]) == 2 and split[3]):
            return False

        date = "-".join(split[:3])
        name = split[-1]
        event = channel.id

        sql = "SELECT ID FROM Event WHERE ID = %s;"
        cursor.execute(sql, [event])

        if cursor.fetchall():
            sql = "DELETE FROM Slot WHERE Event = %s;"
            cursor.execute(sql, [event])
            self.db.commit()

            sql = "DELETE FROM SlotGroup WHERE Event = %s;"
            cursor.execute(sql, [event])
            self.db.commit()

            sql = "DELETE FROM Notify WHERE Event = %s;"
            cursor.execute(sql, [event])
            self.db.commit()

            sql = "UPDATE Event SET Name=%s, Author=%s, Date=%s, Time=%s,Type=%s WHERE ID = %s;"
            var = [channel.name, author.id, date, time, name, event]
            cursor.execute(sql, var)
            self.db.commit()

        else:
            # Check if Author User exists
            sql = "SELECT ID FROM User WHERE ID = %s;"
            cursor.execute(sql, [author.id])

            if not cursor.fetchall():
                sql = "INSERT INTO User (ID, Nickname) VALUES (%s, %s);"
                var = [author.id, author.display_name]
                cursor.execute(sql, var)
                self.db.commit()

            sql = "INSERT INTO Event (ID, Name, Author, Date, Time, Type) VALUES (%s, %s, %s, %s, %s, %s);"
            var = [event, channel.name, author.id, date, time, name]
            cursor.execute(sql, var)

            self.db.commit()

        sql = "SELECT Number, MsgID FROM EventMessage WHERE Event = %s ORDER BY Number;"
        cursor.execute(sql, [channel.id])

        messages = cursor.fetchall()

        if False not in [msg.author == bot for msg in msg_list]:

            for index, elem in enumerate(messages, start=1):
                if index <= len(msg_list):

                    sql = "UPDATE EventMessage SET MsgID = %s WHERE Event = %s AND Number = %s;"
                    var = [msg_list[-index].id, channel.id, elem[0]]

                    cursor.execute(sql, var)
                    self.db.commit()
                else:
                    sql = "DELETE FROM EventMessage WHERE Number = %s"
                    var = [elem[0]]
                    cursor.execute(sql, var)
                    self.db.commit()
        else:
            sql = "DELETE FROM EventMessage WHERE Event = %s"
            var = [channel.id]
            cursor.execute(sql, var)
            self.db.commit()

        content = "\n".join([x.content for x in msg_list[::-1]])

        slots = {}
        struct = []
        last = 0

        current_buffer = ""

        reserve = False

        for line in content.splitlines(False):
            if "Slotliste" in line:
                pass
            elif line and line[0] == "#":
                last, data = get_line_data(line, last, manuel)

                if not struct or current_buffer:
                    struct.append({"Name": "", "Struct": current_buffer, "Length": len(current_buffer)})
                    current_buffer = ""

                    if list(data.values())[0]["Description"].strip().replace("**", "") == "Reserve" and \
                            struct[-1]["Name"].strip().replace("**", "") != "Reserve":
                        struct[-1]["Name"] = "**Reserve**"
                        struct[-1]["Length"] = len(struct[-1]["Struct"]) + len("**Reserve**")

                        reserve = True

                data[list(data)[0]]["GroupNum"] = len(struct) - 1

                struct[-1]["Length"] += len((list(data)[0])) + len(data[list(data)[0]]["Description"]) + 5

                if data[list(data)[0]]["User"]:
                    struct[-1]["Length"] += len(data[list(data)[0]]["User"]) + 1
                    data[list(data)[0]]["User"] = self.get_user_id(data[list(data)[0]]["User"], channel)

                else:
                    data[list(data)[0]]["User"] = None
                    struct[-1]["Length"] += 10  # Average lenght of a Discord Nickname + white space

                slots.update(data)

            elif line.strip() == "":
                current_buffer += "\n"
            else:
                if line.strip().replace("**", "") == "Reserve":
                    reserve = True

                lenght = len(current_buffer) + len(line.strip()) + 1
                struct.append({"Name": line.strip(), "Struct": current_buffer, "Length": lenght})
                current_buffer = ""

        for a, b, c, d, e in [(num, event, elem["Name"], elem["Struct"], elem["Length"]) for num, elem in
                              enumerate(struct, start=0)]:
            sql = "INSERT INTO SlotGroup (Number, Event, Name, Struct, Length) VALUES (%s, %s, %s, %s, %s);"
            var = [a, b, c, d, e]

            cursor.execute(sql, var)
            self.db.commit()

        sql = "INSERT INTO Slot VALUES (%s, %s, %s, %s, %s)"
        var = [(event, index, elem["Description"], elem["User"], elem["GroupNum"]) for index, elem in
               slots.items()]
        cursor.executemany(sql, var)
        self.db.commit()

        # Notify System

        result = datetime.strptime(date + " " + time, '%Y-%m-%d %H:%M:%S')
        delta = timedelta(hours=cfg["std_notify"])

        delta = result - delta

        sql = "INSERT INTO Notify VALUES (%s, %s, %s, %s)"
        var = [(str(event), elem["User"], 1, delta) for index, elem in slots.items() if
               elem["User"] and elem["User"].isdigit()]
        cursor.executemany(sql, var)
        self.db.commit()

        if not reserve:
            lenght = int(len(list(slots)) * self.cfg["res_ratio"]) + 1
            begin = ceil((int(list(slots)[-1]) + 1) / 10) * 10
            msg_format = len(list(slots)[-1]) - 1

            groupNum = len(struct)
            sql = "INSERT INTO SlotGroup (Number, Event, Name, Struct, Length) VALUES (%s, %s, %s, %s, %s);"
            var = [groupNum, channel.id, "Reserve", '\n', lenght * (9 + 14 + len(str(groupNum))) + 12]

            cursor.execute(sql, var)
            self.db.commit()

            sql = "INSERT INTO Slot (Event, Number, Description, GroupNumber) VALUES (%s, %s, %s, %s);"
            var = [(channel.id, str(index).rjust(msg_format, "0"), "Reserve", groupNum) for index in
                   range(begin, begin + lenght)]

            cursor.executemany(sql, var)
            self.db.commit()

        return True

    @with_cursor
    async def write(self, cursor: mysql.connector.MySQLConnection.cursor, channel: discord.TextChannel,
                    manage: bool = False, new: bool = False) -> None:
        """
        Outputs the slotlist to a given channel
        Args:
           cursor: Database cursor
           channel: Server channel
           manage: manage the distribution of slotgroups to msg? (optional)
           new: if its possible to add new msgs (optional)
        """

        locked_modifier = {True: '', False: '**'}

        channel_id = channel.id

        free = self.pull_reserve(channel_id)
        self.sort_reserve(channel)

        if manage:
            sql = "SELECT Number, Length FROM SlotGroup WHERE Event = %s ORDER BY Number;"
            cursor.execute(sql, [channel_id])
            group = cursor.fetchall()

            total = sum([x[1] for x in group])

            sql = "SELECT Number FROM EventMessage WHERE Event = %s;"
            cursor.execute(sql, [channel_id])

            ids = cursor.fetchall()

            if not ids or new:
                number = int((total + 400) / 2000) + 1
                limit = int(total / number)

                ids = []

                for x in range(0, number):
                    sql = "INSERT INTO EventMessage (Event) VALUES (%s);"
                    cursor.execute(sql, [channel_id])
                    self.db.commit()

                    ids.append((cursor.lastrowid,))

            else:

                number = len(ids)
                limit = int(total / number)

            times_limit = 1
            buffer = 0
            last_split = 0

            output = [[]]

            for index, elem in enumerate(group, start=0):
                buffer += elem[1]

                if buffer > limit * times_limit:
                    sql = "UPDATE SlotGroup SET Msg = %s WHERE Event = %s AND Number = %s;"
                    var = [(ids[times_limit - 1][0], channel_id, x[0]) for x in group[last_split:index]]

                    cursor.executemany(sql, var)
                    self.db.commit()

                    last_split = index
                    times_limit += 1
                    output.append([])

                if times_limit >= number:
                    break

            sql = "UPDATE SlotGroup SET Msg = %s WHERE Event = %s AND Number = %s;"
            var = [(ids[times_limit - 1][0], channel_id, x[0]) for x in group[last_split:]]

            cursor.executemany(sql, var)
            self.db.commit()

        sql = "SELECT Number, MsgID FROM EventMessage WHERE Event = %s ORDER BY Number;"
        cursor.execute(sql, [channel_id])
        msgs = cursor.fetchall()

        sql = "SELECT Locked FROM Event WHERE ID =  %s;"
        cursor.execute(sql, [channel_id])
        locked = cursor.fetchone()[0]

        output = "**Slotliste**\n"

        if locked:
            output = "**[Gesperrt]** " + output

        for msg_id in msgs:
            sql = "SELECT Number, Name, Struct, Length FROM SlotGroup WHERE Event = %s AND Msg = %s ORDER BY Number;"
            cursor.execute(sql, [channel_id, msg_id[0]])
            group = cursor.fetchall()

            for element in group:
                if element[1]:
                    if element[1] == "Reserve" and free:
                        continue

                    if element[1] != "":

                        if '\n' in element[2] and element[0] == group[0][0]:
                            output += '\u200B\n'
                        else:
                            output += element[2]

                        output += f"{element[1]}" + "\n"
                else:

                    if '\n' in element[2] and element[0] == group[0][0]:
                        output += '\u200B\n'
                    else:
                        output += element[2]

                sql = "SELECT " \
                      "Number , Description, s.User, GROUP_CONCAT(m.Type SEPARATOR '|') FROM Slot s " \
                      "LEFT JOIN UserEventMark m ON s.User = m.User AND s.Event = m.Event " \
                      "WHERE s.Event = %s AND s.GroupNumber = %s " \
                      "GROUP BY Number " \
                      "ORDER BY CONVERT(Number,UNSIGNED INTEGER);"

                var = [channel_id, element[0]]
                cursor.execute(sql, var)
                slots = cursor.fetchall()
                for x in slots:
                    if x[2] is not None:

                        sql = "SELECT Nickname FROM User WHERE ID = %s;"
                        cursor.execute(sql, [x[2]])
                        user = cursor.fetchone()[0]
                        mark = x[3]
                        output += f"#{x[0]} {x[1]} - {user}"
                        if mark is not None:
                            output += " " + " ".join(
                                [f"<:{x.name}:{x.id}>" if (x := self.util.get_emoji(dict_name=elem)) is not None
                                 else str(elem) for elem in mark.split("|")])

                    else:
                        output += "#{locked}{number} {descr} {locked}- ".format(
                            number=x[0], descr=x[1], locked=locked_modifier[locked])

                    output += "\n"

            if msg_id[1] is not None:

                try:
                    msg = await channel.fetch_message(msg_id[1])
                    await msg.edit(content=output)
                except:
                    msg = await channel.send(output)

                    sql = "UPDATE EventMessage SET MsgID = %s WHERE Number = %s;"
                    var = [msg.id, msg_id[0]]
                    cursor.execute(sql, var)
                    self.db.commit()

            else:
                new_msg = await channel.send(output)

                sql = "UPDATE EventMessage SET MsgID = %s WHERE Number = %s;"
                var = [new_msg.id, msg_id[0]]
                cursor.execute(sql, var)

                self.db.commit()

            output = ""
