import asyncio
import datetime
import difflib
import os
import pickle
import random
import traceback
from enum import Enum
from typing import List, Coroutine

import discord


class LanguageUtils:
    @staticmethod
    def pluralize(number: int, nom_sing: str, gen_sing: str, gen_pl: str) -> str:
        s_last_digit = str(number)[-1]

        pluralized: str

        if int(str(number)[-2:]) in range(11, 20):
            # 11-19
            pluralized = gen_pl
        elif s_last_digit == '1':
            # 1
            pluralized = nom_sing
        elif int(s_last_digit) in range(2, 5):
            # 2,3,4
            pluralized = gen_sing
        else:
            # 5,6,7,8,9,0
            pluralized = gen_pl

        return "%s %s" % (number, pluralized)

    @staticmethod
    def formatted_duration(secs: int) -> str:
        days = round(secs // 86400)
        hours = round((secs - days * 86400) // 3600)
        minutes = round((secs - days * 86400 - hours * 3600) // 60)
        seconds = round(secs - days * 86400 - hours * 3600 - minutes * 60)

        days_text = LanguageUtils.pluralize(days, "день", "дня", "дней")
        hours_text = LanguageUtils.pluralize(hours, "час", "часа", "часов")
        minutes_text = LanguageUtils.pluralize(minutes, "минута", "минуты", "минут")
        seconds_text = LanguageUtils.pluralize(seconds, "секунда", "секунды", "секунд")

        formatted = ", ".join(filter(lambda x: bool(x), [days_text if days else "",
                                                         hours_text if hours else "",
                                                         minutes_text if minutes else "",
                                                         seconds_text if seconds else ""]))

        return formatted


class Logger:
    name: str

    class Colors(Enum):
        BLUE = "\033[94m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        ENDC = "\033[0m"
        GREEN = '\033[92m'

    def __init__(self, name: str):
        self.name = name

    def log(self, message: str, message_type: str, color: str):
        print("%s[%s] [%s\\%s]: %s%s" % (color,
                                         datetime.datetime.now().strftime("%d.%m.%G %H:%M:%S.%f")[:-3], self.name,
                                         message_type, message,
                                         self.Colors.ENDC.value))

    def info(self, message: str):
        self.log(message, "INFO", self.Colors.BLUE.value)

    def warn(self, message: str):
        self.log(message, "WARN", self.Colors.YELLOW.value)

    def error(self, message: str):
        self.log(message, "ERROR", self.Colors.RED.value)

    def ok(self, message: str):
        self.log(message, "OK", self.Colors.GREEN.value)


class Module:
    name: str
    description: str
    bot = None
    logger: Logger
    tasks = []

    def __init__(self, bot):
        self.bot = bot
        self.tasks = []

    async def on_enable(self):
        pass

    async def on_discord_event(self, event_name, *args, **kwargs):
        pass


class ModuleHandler:
    modules: List[Module] = []
    logger: Logger
    params_file = "./params.pkl"
    params = {}

    def __init__(self):
        self.logger = Logger("ModuleHandler")

    def load_modules(self):
        pass

    def load_module(self, module: Module):
        self.modules.append(module)

    def unload_module(self, module: Module):
        for task in list(module.tasks):
            task.cancel()
            module.tasks.remove(task)

            self.logger.info("Отменён таск модуля %s" % module.name)

        self.modules.remove(module)

        self.logger.info("Отгружен модуль %s" % module.name)

    async def __wait_for_task_to_end(self, module, task):
        await task

        if task in module.tasks:
            module.tasks.remove(task)

    async def add_background_task(self, coro: Coroutine, module: Module):
        task = asyncio.ensure_future(coro)

        module.tasks.append(task)

        asyncio.ensure_future(self.__wait_for_task_to_end(module, task))

    def add_param(self, key: str, value_default):
        if key not in self.params:
            self.set_param(key, value_default, True)

    def set_param(self, key: str, value, save=False):
        self.params[key] = value

        if save:
            self.save_params()

    def get_param(self, key: str):
        return self.params[key]

    def save_params(self):
        with open(self.params_file, "wb") as f:
            pickle.dump(self.params, f)

    def load_params(self):
        if not os.path.isfile(self.params_file):
            self.save_params()
        else:
            with open(self.params_file, "rb") as f:
                self.params = pickle.load(f)


class PermissionHandler:
    def has_permission(self, member: discord.Member) -> bool:
        pass


class AcceptAllPermissionHandler(PermissionHandler):
    def has_permission(self, member: discord.Member) -> bool:
        return True


class DiscordPermissionHandler(PermissionHandler):
    permissions: List[str] = []

    def __init__(self, permissions: List[str]):
        self.permissions = permissions

    def has_permission(self, member: discord.Member) -> bool:
        for k, v in iter(member.guild_permissions):
            if k in self.permissions and not v:
                return False

        return True


class EmbedType(Enum):
    OK = (discord.colour.Color.green(), "ОК")
    INFO = (0, "Инфо")
    ERROR = (discord.colour.Color.red(), "Ошибка")


class CommandContext:
    message: discord.Message
    abstract_content: str
    command_str: str
    args: List[str]
    clean_args: List[str]
    keys: List[str]

    def __init__(self, message: discord.Message, command_str: str, args: List[str], clean_args: List[str],
                 keys: List[str], abstract_content: str):
        self.message = message
        self.args = args
        self.clean_args = clean_args
        self.keys = keys
        self.command_str = command_str
        self.abstract_content = abstract_content

    def get_custom_embed(self, message: str, title: str, color: int) -> discord.Embed:
        embed = discord.Embed(color=color, description=message, title="**%s**" % title)

        embed.set_footer(icon_url=self.message.author.avatar_url, text="Запросил: %s" % "%s#%s" % (
            self.message.author.display_name, self.message.author.discriminator))

        return embed

    def get_embed(self, embed_type: EmbedType, message: str, title: str = None):
        color = self.message.guild.me.top_role.color if embed_type == EmbedType.INFO else embed_type.value[0]

        return self.get_custom_embed(message, embed_type.value[1] if title is None else title, color)

    async def send_embed(self, embed_type: EmbedType, message: str, title: str = None):
        await self.message.channel.send(embed=self.get_embed(embed_type, message, title))

    async def send(self, message: str, reply: bool = False):
        await self.message.channel.send(("%s, %s" % (self.message.author.mention, message)) if reply else message)


class ContextGenerator:
    def process_message(self, message: discord.Message) -> CommandContext:
        pass


class PrefixContextGenerator(ContextGenerator):
    prefix: str

    def __init__(self, prefix: str):
        self.prefix = prefix

    def process_message(self, message: discord.Message):
        if not message.content.startswith(self.prefix):
            return None

        args = message.content.split()
        clean_args = message.content.split()[1:]
        command = args.pop(0)[len(self.prefix):].lower()

        keys = []
        for arg in args:
            if arg.startswith("--") and len(arg) > 2 and arg not in keys:
                keys.append(arg)

        for i, key in enumerate(keys):
            args.remove(key)
            keys[i] = key[2:]

        return CommandContext(message, command, args, clean_args, keys, message.content[len(self.prefix):])


class CommandResult:
    error: bool
    args_error: bool
    access_denied: bool
    embed_type: EmbedType
    message: str
    title: str
    color: int

    def __init__(self, error: bool, message: str, embed_type: EmbedType, title: str = None, color: int = None,
                 args_error: bool = False, access_denied: bool = False):
        self.error = error
        self.message = message
        self.title = title
        self.color = color
        self.embed_type = embed_type
        self.args_error = args_error
        self.access_denied = access_denied

    @staticmethod
    def ok(message: str = None, title: str = None, color: int = None):
        return CommandResult(False, message, EmbedType.OK, title, color)

    @staticmethod
    def info(message: str = None, title: str = None, color: int = None):
        return CommandResult(False, message, EmbedType.INFO, title, color)

    @staticmethod
    def error(message: str = None, title: str = None, color: int = None):
        return CommandResult(True, message, EmbedType.ERROR, title, color)

    @staticmethod
    def args_error(message: str = None):
        return CommandResult(True, message, EmbedType.ERROR, "Недостаточно аргументов!", args_error=True)

    @staticmethod
    def access_denied():
        return CommandResult(True, "", embed_type=EmbedType.ERROR, access_denied=True)


class Command:
    name: str
    description: str
    args_description: str
    keys_description: List[str]
    perm_handler: PermissionHandler
    module: Module
    should_await: bool

    def __init__(self, name: str, description: str, args_description: str, keys_description: List[str],
                 perm_handler: PermissionHandler, module: Module, should_await: bool):
        self.name = name
        self.description = description
        self.args_description = args_description
        self.keys_description = keys_description
        self.perm_handler = perm_handler
        self.module = module
        self.should_await = should_await

    async def execute(self, ctx: CommandContext) -> CommandResult:
        pass

    def get_detailed_name(self) -> str:
        name = self.name

        if len(self.args_description):
            name += " %s" % self.args_description

        if len(self.keys_description):
            name += " [%s]" % "/".join(self.keys_description)

        return name


class CommandHandler:
    emojis = {
        "ok": "☑",
        "error": "❌",
        "access_denied": "🚫",
        "args_error": "⁉"
    }

    access_denied_messages = ["Нет прав!", "Прав не завезли.", "Вы точно уверены? (да/нет)", "Что-то пошло не так. "
                                                                                             "Попробуйте позже",
                              "Увы, но ты слишком мелковат для этого действия.",
                              "Действие НЕ выполнено. Не знаю, почему.",
                              "[ACCESS DENIED!](https://www.youtube.com/watch?v=2dZy3cd9KFY)"]

    commands = {}
    context_generator: ContextGenerator
    whitelist = []
    logger: Logger

    def __init__(self, context_generator: ContextGenerator, whitelist: List[int]):
        self.context_generator = context_generator
        self.whitelist = whitelist
        self.logger = Logger('CommandHandler')

    async def handle(self, message: discord.Message):
        context = self.context_generator.process_message(message)

        if not context or not isinstance(message.author, discord.Member) or len(
                message.content) < 2 or message.author is message.guild.me:
            return

        result: CommandResult
        emoji = None
        command = None

        if message.guild.id not in self.whitelist:
            result = CommandResult.error("Этот сервер не состоит в белом списке разрешенных серверов бота.")
        elif context.command_str not in self.commands:
            similar_commands = []

            for command in list(self.commands.values()):
                ratio = difflib.SequenceMatcher(None, context.command_str, command.name).ratio()

                if ratio > 0.5:
                    similar_commands.append("%s (%s)" % (command.name, ratio))

            result = CommandResult.error("Ты %s\n%s" % (
                context.abstract_content,
                ("Возможно, вы имели в виду: %s" % ", ".join(similar_commands)) if len(
                    similar_commands) else ""),
                                         "Команда не найдена!")
        else:
            command = self.commands[context.command_str]

            if not command.perm_handler.has_permission(message.author):
                result = CommandResult.error(random.choice(self.access_denied_messages), "Нет прав!")
                emoji = self.emojis["access_denied"]
            else:
                if command.should_await:
                    try:
                        result = await command.execute(context)
                    except discord.Forbidden:
                        result = CommandResult.error("У бота нет прав, чтобы совершить это действие!")
                    except Exception:
                        result = CommandResult.error(
                            "Техническая информация/Stacktrace: \n```%s```" % traceback.format_exc(),
                            "⚠ Не удалось выполнить команду ⚠")

                    if result.access_denied:
                        result = CommandResult.error(random.choice(self.access_denied_messages), "Нет прав!")
                        emoji = self.emojis["access_denied"]
                else:
                    asyncio.ensure_future(command.execute(context))
                    result = CommandResult.ok()

        embed = context.get_embed(result.embed_type, result.message, result.title)

        if result.args_error and command:
            emoji = self.emojis["args_error"]

            embed.add_field(
                name=command.get_detailed_name(),
                value=command.description, inline=False)

        if result.title is not None or result.message is not None:
            await message.channel.send(embed=embed)

        try:
            await message.add_reaction(emoji if emoji else self.emojis["error"] if result.error else self.emojis["ok"])
        except discord.NotFound:
            pass

    def register_command(self, command: Command):
        self.commands[command.name] = command

    def unregister_command(self, command: Command):
        del self.commands[command.name]

        self.logger.info("Отгружена команда %s модуля %s" % (command.name, command.module.name))

    def unregister_module_commands(self, module_name: str):
        for command in list(self.commands.values()):
            if command.module.name == module_name:
                self.unregister_command(command)


class Bot(discord.Client):
    name = ""

    module_handler: ModuleHandler
    command_handler: CommandHandler

    logger: Logger

    start_time: float

    def __init__(self, name: str, module_handler: ModuleHandler,
                 command_handler: CommandHandler, start_time: float):
        super().__init__()

        self.name = name
        self.module_handler = module_handler
        self.command_handler = command_handler
        self.start_time = start_time

        self.logger = Logger(self.name)

    async def run_modules_event(self, event_name, *args, **kwargs):
        for module in self.module_handler.modules:
            try:
                await module.on_discord_event(event_name, *args, **kwargs)
            except Exception:
                self.logger.error(
                    "Ошибка при выполнении ивента %s модулем %s:\n%s" % (
                        event_name, module.name, traceback.format_exc()))

    def dispatch(self, event, *args, **kwargs):
        method = 'on_' + event

        super().dispatch(event, *args, **kwargs)

        asyncio.ensure_future(self.run_modules_event(method, *args, **kwargs))