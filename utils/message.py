"""
utils/message.py
────────────────
Pre-rendered message constants for the entire bot.

All values are static constants generated at import time.

Integrates styling patterns from:
  - Moon-Userbot  : HTML bold/italic structure, code-block formatting
  - Dragon-Userbot: Clean <b>label:</b> <i>value</i> convention
  - CatUserBot    : Unicode font tables (smallcaps, cursive, fraktur,
                    gothic, bubbles, superscript) for decorative labels

Usage:
    from utils.message import Msg, font

    await message.edit(Msg.ERR_NO_GROUP_CALL)
    await message.edit(Msg.ERR_ADMIN_REQUIRED)
    styled = font.smallcaps("Hello World")
    styled = font.bold_cursive("Playing")
"""
import re
import html

from utils.custom_emojis import (
    CAT,
    CROWN,
    DOWNLOAD,
    DRAGON,
    ERROR,
    FIRE,
    FOLDER,
    GEAR,
    HEART,
    INFO,
    LOADING,
    LOCK,
    USER,
    MIC,
    NOTE,
    MOON,
    MUSIC,
    CHAT,
    LINK,
    ID,
    PIN,
    PARTY,
    ROCKET,
    SHIELD,
    SPARK,
    STAR,
    SEARCH,
    GRID,
    PUZZLE,
    SOLVE,
    PONG,
    SUCCESS,
    THUMBS_UP,
    WARNING,
    WARNING_BOLT,
    WAVE,
    CALENDAR,
    QUESTION,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unicode font-style helpers  (ported from CatUserBot's helpers/fonts.py)
# ─────────────────────────────────────────────────────────────────────────────

_NORMAL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

_SMALLCAPS = "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789"
_BOLD_CURSIVE = "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃0123456789"
_DOUBLE = "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"


def _translate(text: str, source: str, target) -> str:
    """Map each character in text through the font table."""
    out = []
    for ch in text:
        idx = source.find(ch)
        if idx >= 0:
            out.append(target[idx])
        else:
            out.append(ch)
    return "".join(out)


class _Font:
    """
    Lightweight font-style converter.

    Inspired by CatUserBot's helpers/fonts.py — provides Unicode
    "font" transformations that render distinctively in Telegram.
    """

    def smallcaps(self, text: str) -> str:
        """ᴀʙᴄᴅᴇꜰ — Small-caps style (upper & lower → phonetic IPA)"""
        return _translate(text, _NORMAL, _SMALLCAPS)

    def bold_cursive(self, text: str) -> str:
        """𝓑𝓸𝓵𝓭 𝓒𝓾𝓻𝓼𝓲𝓿𝓮 — Bold cursive/calligraphic style"""
        return _translate(text, _NORMAL, _BOLD_CURSIVE)

    def double(self, text: str) -> str:
        """𝔻𝕠𝕦𝕓𝕝𝕖 — Double-struck style"""
        return _translate(text, _NORMAL, _DOUBLE)


#: Singleton instance; import and call methods directly.
font = _Font()


# ─────────────────────────────────────────────────────────────────────────────
# Message constants
# ─────────────────────────────────────────────────────────────────────────────

class Msg:
    """
    Centralised message constant store.

    Naming convention (matches Moon-Userbot + Dragon-Userbot patterns):
      ERR_*    → error messages
      WARN_*   → warning / access-denied messages
      OK_*     → success confirmations
      INFO_*   → neutral informational messages

    Prefix labels use:
      • Telegram custom emoji tags for Premium emoji display
      • Unicode smallcaps label text (CatUserBot style) for non-premium fallback
      • HTML <b>/<i> wrapping (Dragon-Userbot / Moon-Userbot style)
      • Box-drawing/arrow characters for visual hierarchy
    """

    # ── Custom emoji labels backed by sticker pack ids ──────────────────────
    EMOJI_ERROR   = ERROR
    EMOJI_WARNING = WARNING
    EMOJI_SUCCESS = SUCCESS
    EMOJI_INFO    = INFO

    EMOJI_LOADING = LOADING
    EMOJI_PIN     = PIN
    EMOJI_ROCKET  = ROCKET
    EMOJI_GEAR    = GEAR
    EMOJI_FIRE    = FIRE
    EMOJI_SPARK   = SPARK
    EMOJI_MUSIC   = MUSIC
    EMOJI_MIC     = MIC
    EMOJI_SHIELD  = SHIELD
    EMOJI_LOCK    = LOCK
    EMOJI_CROWN   = CROWN
    EMOJI_DRAGON  = DRAGON
    EMOJI_MOON    = MOON
    EMOJI_CAT     = CAT
    EMOJI_THUMBS_UP = THUMBS_UP
    EMOJI_HEART   = HEART
    EMOJI_PARTY   = PARTY
    EMOJI_WARNING_BOLT = WARNING_BOLT
    EMOJI_FOLDER  = FOLDER
    EMOJI_DOWNLOAD = DOWNLOAD
    EMOJI_NOTE    = NOTE
    EMOJI_WAVE    = WAVE
    EMOJI_CALENDAR = CALENDAR
    EMOJI_QUESTION = QUESTION
    EMOJI_STAR    = STAR
    EMOJI_SEARCH  = SEARCH
    EMOJI_GRID    = GRID
    EMOJI_PUZZLE  = PUZZLE
    EMOJI_SOLVE   = SOLVE
    EMOJI_USER    = USER
    EMOJI_CHAT    = CHAT
    EMOJI_LINK    = LINK
    EMOJI_ID      = ID
    EMOJI_PONG    = PONG


    # ── Prefix labels (Unicode smallcaps label + emoji + box-draw) ───────────
    # Combine: Dragon-Userbot's <b>label:</b> <i>value</i> convention with
    # CatUserBot's Unicode font style for the label itself.
    _ERR_LABEL  = f"<b>{font.smallcaps('Error')}</b>"
    _WARN_LABEL = f"<b>{font.smallcaps('Warning')}</b>"
    _OK_LABEL   = f"<b>{font.smallcaps('Success')}</b>"
    _INFO_LABEL = f"<b>{font.smallcaps('Info')}</b>"

    ERROR_PREFIX   = f'{EMOJI_ERROR} {_ERR_LABEL}\n╰▸ '
    WARNING_PREFIX = f'{EMOJI_WARNING} {_WARN_LABEL}\n╰▸ '
    SUCCESS_PREFIX = f'{EMOJI_SUCCESS} {_OK_LABEL}\n╰▸ '
    INFO_PREFIX    = f'{EMOJI_INFO} {_INFO_LABEL}\n╰▸ '

    # ── Errors ───────────────────────────────────────────────────────────────
    ERR_ADMIN_REQUIRED        = f'{ERROR_PREFIX}Admin Privileges Required'
    ERR_REPLY_USER_OR_ID      = f'{ERROR_PREFIX}Reply To User Or Provide Username/ID'
    ERR_REPLY_USER_ID         = f'{ERROR_PREFIX}Reply To User Or Provide User ID'
    ERR_NO_INLINE_RESULTS     = f'{ERROR_PREFIX}No Inline Results Found'
    ERR_NO_DATA               = f'{ERROR_PREFIX}No Data Found'
    ERR_INVALID_COUNT         = f'{ERROR_PREFIX}Invalid Count Number'
    ERR_FILE_TOO_LARGE        = f'{ERROR_PREFIX}File Exceeds 2GB Limit. Upgrade To Telegram Premium.'
    ERR_FILE_EXCEEDS_2GB      = f'{ERROR_PREFIX}File Exceeds 2GB Limit'
    ERR_STICKER_ADD_FAILED    = f'{ERROR_PREFIX}Failed. Use @Stickers Bot To Add Sticker.'
    ERR_COUNT_1_100           = f'{ERROR_PREFIX}Count Must Be 1-100'
    ERR_INVALID_COUNT_NUMBER  = f'{ERROR_PREFIX}Invalid Count! Use A Number'
    ERR_CANT_FETCH_USER       = f'{ERROR_PREFIX}Cannot Fetch User From Entity'
    ERR_NO_GROUP_CALL         = f'{ERROR_PREFIX}No Active Group Call Found'
    ERR_QUOTE_FAILED          = f'{ERROR_PREFIX}Quote Generation Failed'
    ERR_REPLY_PHOTO_OR_STICKER= f'{ERROR_PREFIX}Reply To Any Photo Or Sticker'
    ERR_REPLY_USER_MSG        = f"{ERROR_PREFIX}Reply To A User's Message"
    ERR_REPLY_TO_QUOTE        = f'{ERROR_PREFIX}Reply To A Message To Create A Quote'
    ERR_NO_TEXT_TO_QUOTE      = f'{ERROR_PREFIX}No Text Found To Quote'
    ERR_GET_USER_INFO_FAILED  = f'{ERROR_PREFIX}Failed To Get User Info'
    ERR_GENERATE_QUOTE_FAILED = f'{ERROR_PREFIX}Failed To Generate Quote'
    ERR_QUOTE_RETRIES_FAILED  = f'{ERROR_PREFIX}Failed After Multiple Retries'
    ERR_START_CALL_FAILED     = f'{ERROR_PREFIX}Failed To Start Group Call'
    ERR_INVALID_CHAT_ID       = f'{ERROR_PREFIX}Invalid Chat ID. Provide A Valid Integer.'
    ERR_NO_BLACKLIST          = f'{ERROR_PREFIX}No Blacklist Found'
    ERR_REPLY_TO_STICKER      = f'{ERROR_PREFIX}Reply To Any Sticker'
    ERR_STICKER_NO_NAME       = f'{ERROR_PREFIX}Sticker Has No Name'
    ERR_UNSUPPORTED_FILE      = f'{ERROR_PREFIX}Unsupported File Type'
    ERR_REPLY_PHOTO_STICKER   = f'{ERROR_PREFIX}Reply To Photo/GIF/Sticker'
    ERR_PURGE_REPLY           = f'{ERROR_PREFIX}Reply To A Message To Start Purging'
    ERR_REPLY_PURGE_USER      = f"{ERROR_PREFIX}Reply To A User's Message To Delete All Their Messages"
    ERR_DELETE_REPLY          = f'{ERROR_PREFIX}Reply To A Message To Delete It'
    ERR_UNKNOWN_STYLE         = f'{ERROR_PREFIX}Unknown Style. Use [Prefix]Fonts To See Styles'
    ERR_SPECIFY_USER          = f'{ERROR_PREFIX}Specify A User To Clone'
    ERR_CANT_CLONE_ADMIN      = f'{ERROR_PREFIX}Cannot Clone Admin User'
    ERR_NO_CLONE_DATA         = f'{ERROR_PREFIX}No Clone Data Found'
    ERR_OWNER_ONLY            = f'{ERROR_PREFIX}Owner-Only Command'
    ERR_PROVIDE_SPAM_TEXT     = f'{ERROR_PREFIX}Provide Something To Spam'
    ERR_INVALID_DELAY         = f'{ERROR_PREFIX}Invalid Delay Value'
    ERR_GCAST_FLAG            = f'{ERROR_PREFIX}Provide Gcast Flag'
    ERR_GCAST_USAGE           = f'{ERROR_PREFIX}Usage: [Prefix]Gcast [-All|-Pvt|-Grp] [Message/Reply]'
    ERR_SCHEDULE_FORMAT       = f'{ERROR_PREFIX}Invalid Format! Use: [Prefix]Schedule <Target> <HH:MM:SS> <MSG>'
    ERR_SCHEDULE_TIME         = f'{ERROR_PREFIX}Invalid Time! Use HH:MM:SS Or HH:MM:SS:CC (24-Hour)'
    ERR_SANGMATA_BLOCKED      = f'{ERROR_PREFIX}Bot Is Blocked. Unblock @Sangmata_Beta_Bot And Try Again.'
    ERR_INVALID_CHANNEL       = f'{ERROR_PREFIX}Invalid Channel Or Group'
    ERR_MMF_USAGE             = f'{ERROR_PREFIX}Usage: [Prefix]MMF <Text>'
    ERR_UNBAN_PERMISSION      = f'{ERROR_PREFIX}Need Manage Users Permission To Unban'

    # ── Admin Action Errors ──────────────────────────────────────────────────
    ERR_CANT_BAN_ADMIN      = f'{ERROR_PREFIX}Cannot Ban This Admin'
    ERR_CANT_KICK_ADMIN     = f'{ERROR_PREFIX}Cannot Kick This Admin'
    ERR_CANT_MUTE_ADMIN     = f'{ERROR_PREFIX}Cannot Mute This Admin'
    ERR_CANT_UNMUTE_ADMIN   = f'{ERROR_PREFIX}Cannot Unmute This Admin'
    ERR_CANT_VERIFY_ADMIN   = f'{ERROR_PREFIX}Cannot Verify Admin Privileges'
    ERR_USER_ALREADY_ADMIN  = f'{ERROR_PREFIX}User Already Admin Or Cannot Be Promoted'
    ERR_NO_ADMIN_RIGHTS_PIN = f'{ERROR_PREFIX}Need Admin Rights To Pin'
    ERR_NO_ADMIN_RIGHTS_UNPIN= f'{ERROR_PREFIX}Need Admin Rights To Unpin'
    ERR_NO_GRANT_PRIVILEGES = f'{ERROR_PREFIX}No Privileges To Grant'
    ERR_REPLY_TO_PIN        = f'{ERROR_PREFIX}Reply To A Message To Pin It'
    ERR_IMAGE_DOC_ONLY      = f'{ERROR_PREFIX}Document Must Be An Image Type'
    ERR_REPLY_IMAGE_DOC     = f'{ERROR_PREFIX}Reply To An Image/Document'
    ERR_PROVIDE_EVAL_CODE   = f'{ERROR_PREFIX}Provide Code To Evaluate'
    ERR_GCAST_NOTHING       = f'{ERROR_PREFIX}Nothing Given To Gcast'
    ERR_CANT_DM_RAID_OWNER  = f'{ERROR_PREFIX}Cannot DM Raid The Owner'
    ERR_CANT_DM_SPAM_OWNER  = f'{ERROR_PREFIX}Cannot DM Spam The Owner'
    ERR_PRIVACY_HISTORY     = f'{ERROR_PREFIX}Unable To Retrieve History. User May Have Privacy Enabled.'
    ERR_GROUP_ONLY          = f'{ERROR_PREFIX}Group Only'
    ERR_INVALID_COMMAND     = f'{ERROR_PREFIX}Invalid Command'
    ERR_INVALID_NUMBER      = f'{ERROR_PREFIX}Invalid Number'
    ERR_NO_RESULTS          = f'{ERROR_PREFIX}No Results Found'
    ERR_UNSUPPORTED_MEDIA   = f'{ERROR_PREFIX}Unsupported Media Type'

    # ── Warnings ─────────────────────────────────────────────────────────────
    WARN_NOT_AUTHORIZED    = f'{WARNING_PREFIX}Not Authorized'
    WARN_PRIVATE_RESTRICTED= f'{WARNING_PREFIX}Private Chat Restricted'
    WARN_SESSION_NOT_FOUND = f'{WARNING_PREFIX}Session Not Found'
    WARN_RESTRICTED_DMS    = f'{WARNING_PREFIX}Restricted In DMs'
    WARN_CMD_NOT_FOUND     = f'{WARNING_PREFIX}Command Not Found'
    WARN_VC_JOIN_FIRST     = f'{WARNING_PREFIX}Join The Group Call Before Inviting Users'
    WARN_NO_QUERY          = f'{WARNING_PREFIX}No Query Provided'
    WARN_REACTIONS_DISABLED= f'{WARNING_PREFIX}Reactions Disabled'

    # ── Success ───────────────────────────────────────────────────────────────
    OK_USERBOT_STOPPED      = f'{SUCCESS_PREFIX}Userbot Stopped'
    OK_USERBOT_REBOOTED     = f'{SUCCESS_PREFIX}Userbot Rebooted'
    OK_STICKER_KANGED       = f'{SUCCESS_PREFIX}Sticker Kanged'
    OK_APPROVED_WHITELIST   = f'{SUCCESS_PREFIX}Approved & Added To Whitelist'
    OK_REMOVED_WHITELIST    = f'{SUCCESS_PREFIX}Removed From Whitelist & Count Reset'
    OK_ALL_WHITELIST_CLEARED= f'{SUCCESS_PREFIX}All Whitelisted Users Removed'
    OK_COUNTS_RESET         = f'{SUCCESS_PREFIX}All Message Counts Reset To 0'
    OK_COUNT_RESET          = f'{SUCCESS_PREFIX}Message Count Reset To 0'
    OK_PROFILE_REVERTED     = f'{SUCCESS_PREFIX}Profile Reverted'
    OK_MSG_UNPINNED         = f'{SUCCESS_PREFIX}Message Unpinned'
    OK_GROUP_CALL_ENDED     = f'{SUCCESS_PREFIX}Group Call Ended'
    OK_MENTION_DISMISSED    = f'{SUCCESS_PREFIX}Mention Dismissed'
    OK_ALIVE_RESET          = f'{SUCCESS_PREFIX}Alive Keys Reset (Emoji, Text)'
    OK_WELCOME_RESET        = f'{SUCCESS_PREFIX}Welcome Reset'
    OK_SETTINGS_SAVED       = f'{SUCCESS_PREFIX}Settings Saved'
    OK_JOIN_REQUESTS_DONE   = f'{SUCCESS_PREFIX}Join Requests Processed'
    OK_DM_SPAM_DONE         = f'{SUCCESS_PREFIX}DM Spam Done'
    OK_DM_RAID_DONE         = f'{SUCCESS_PREFIX}DM Raid Done'
    OK_MSG_PINNED           = f'{SUCCESS_PREFIX}Message Pinned'
    OK_ALL_MSGS_UNPINNED    = f'{SUCCESS_PREFIX}All Messages Unpinned'
    OK_LATEST_PIN_UNPINNED  = f'{SUCCESS_PREFIX}Latest Pin Unpinned'
    OK_REACTION_UPDATED     = f'{SUCCESS_PREFIX}Reaction Updated'
    OK_REACTIONS_ENABLED    = f'{SUCCESS_PREFIX}Reactions Enabled'
    OK_SUDO_GRANTED         = f'{SUCCESS_PREFIX}Sudo Granted'
    OK_SUDO_REVOKED         = f'{SUCCESS_PREFIX}Sudo Revoked'
    OK_JOIN_REQUESTS_EMPTY  = f'{SUCCESS_PREFIX}No Pending Join Requests'
    OK_REPLY_RAID_ACTIVATED   = f'{SUCCESS_PREFIX}Reply Raid Activated'
    OK_REPLY_RAID_DEACTIVATED = f'{SUCCESS_PREFIX}Reply Raid Deactivated'

    # ── Info ──────────────────────────────────────────────────────────────────
    INFO_REPLY_RAID_ACTIVE  = f'{INFO_PREFIX}Reply Raid Already Active For This User'
    INFO_NO_REPLY_RAID      = f'{INFO_PREFIX}No Reply Raid Active For This User'
    INFO_BLACKLIST_EMPTY    = f'{INFO_PREFIX}Blacklist Is Empty'
    INFO_NOT_IN_WHITELIST   = f'{INFO_PREFIX}Not In Whitelist'
    INFO_ALREADY_WHITELISTED= f'{INFO_PREFIX}Already In Whitelist'
    INFO_NO_COUNT           = f'{INFO_PREFIX}No Count Found For This Chat'
    INFO_TAGALL_INACTIVE    = f'{INFO_PREFIX}No Active Tagall Here'
    INFO_WORDLIST_EMPTY     = f'{INFO_PREFIX}Word List Already Empty'
    INFO_NOT_AFK            = f"{INFO_PREFIX}You Weren't AFK"
    INFO_NO_BANNED_USERS    = f'{INFO_PREFIX}No Banned Users Found'
    INFO_ALREADY_SUDOER     = f'{INFO_PREFIX}Already A Sudoer'
    INFO_NOT_A_SUDOER       = f'{INFO_PREFIX}Not A Sudoer'
    INFO_NO_SUDOERS         = f'{INFO_PREFIX}No Sudoers Found'
    INFO_NO_WHITELIST_USERS = f'{INFO_PREFIX}No Whitelisted Users To Remove'
    INFO_NO_PENDING_JOIN_REQ= f'{INFO_PREFIX}No Pending Join Requests'

    # ─────────────────────────────────────────────────────────────────────────
    # Composite / rich-text formatters
    # These follow Dragon-Userbot's <b>label:</b> <i>value</i> convention,
    # whilst using Unicode labels (CatUserBot style) for the label text.
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def afk_notify(afk_time: str, reason: str) -> str:
        """AFK auto-reply (Dragon-Userbot style)."""
        label_afk    = font.smallcaps("I'm AFK")
        label_reason = font.smallcaps("Reason")
        return (
            f"<b>{label_afk}</b> {afk_time}\n"
            f"<b>{label_reason}:</b> <i>{reason}</i>"
        )

    @staticmethod
    def afk_gone(reason: str) -> str:
        """Set-AFK confirmation (Dragon-Userbot style)."""
        label_going  = font.smallcaps("Going AFK")
        label_reason = font.smallcaps("Reason")
        return (
            f"<b>{label_going}</b>\n"
            f"<b>{label_reason}:</b> <i>{reason}</i>"
        )

    @staticmethod
    def afk_return(afk_time: str) -> str:
        """Un-AFK confirmation."""
        label = font.smallcaps("No Longer AFK")
        label_was = font.smallcaps("Was away for")
        return (
            f"<b>{label}</b>\n"
            f"<b>{label_was}:</b> <i>{afk_time}</i>"
        )

    @staticmethod
    def pong(latency_ms: float) -> str:
        """Ping result (Moon-Userbot style)."""
        label   = font.smallcaps("Pong")
        lat_lbl = font.smallcaps("Latency")
        return f"<b>{label}!</b> <code>{latency_ms:.0f}ms</code>"

    @staticmethod
    def banned(user: str, reason: str = "No reason given") -> str:
        """Ban confirmation (Dragon-Userbot style)."""
        label_banned = font.smallcaps("Banned")
        label_reason = font.smallcaps("Reason")
        return (
            f"<b>{label_banned}:</b> {user}\n"
            f"<b>{label_reason}:</b> <i>{reason}</i>"
        )

    @staticmethod
    def unbanned(user: str) -> str:
        """Unban confirmation."""
        label = font.smallcaps("Unbanned")
        return f"<b>{label}:</b> {user}"

    @staticmethod
    def muted(user: str, duration: str = "indefinitely") -> str:
        """Mute confirmation (Dragon-Userbot style)."""
        label_muted = font.smallcaps("Muted")
        label_dur   = font.smallcaps("Duration")
        return (
            f"<b>{label_muted}:</b> {user}\n"
            f"<b>{label_dur}:</b> <i>{duration}</i>"
        )

    @staticmethod
    def unmuted(user: str) -> str:
        """Unmute confirmation."""
        label = font.smallcaps("Unmuted")
        return f"<b>{label}:</b> {user}"

    @staticmethod
    def promoted(user: str, title: str = "") -> str:
        """Promote confirmation."""
        label = font.smallcaps("Promoted")
        base  = f"<b>{label}:</b> {user}"
        return f"{base} — <i>{title}</i>" if title else base

    @staticmethod
    def demoted(user: str) -> str:
        """Demote confirmation."""
        label = font.smallcaps("Demoted")
        return f"<b>{label}:</b> {user}"

    @staticmethod
    def kicked(user: str) -> str:
        """Kick confirmation."""
        label = font.smallcaps("Kicked")
        return f"<b>{label}:</b> {user}"

    @staticmethod
    def loading(action: str = "Processing") -> str:
        """Inline loading status (Moon-Userbot style)."""
        label = font.smallcaps(action)
        return f'{Msg.EMOJI_LOADING} <i>{label}…</i>'
    @staticmethod
    def card(title: str, lines, emoji: str = PIN, footer: str = "") -> str:
        """Build a compact HTML status card with consistent spacing."""
        body_lines = []
        for line in lines:
            if line:
                body_lines.append(f"┃ {line}")
        if footer:
            body_lines.append(f"╰▸ {footer}")
        else:
            body_lines.append("╰━━━━━━━━━━━━━━━━━━━━╯")

        return "\n".join([
            f"{emoji} <b>{font.smallcaps(title)}</b>",
            *body_lines,
        ])

    @staticmethod
    def now_playing(title: str, artist: str = "", duration: str = "") -> str:
        """
        Now-playing card using cursive font for title
        (CatUserBot album/music display style).
        """
        t = font.bold_cursive(title[:40])
        parts = [f'{Msg.EMOJI_MUSIC} <b>{t}</b>']
        if artist:
            a = font.smallcaps(artist)
            parts.append(f'{Msg.EMOJI_MIC} <i>{a}</i>')
        if duration:
            parts.append(f'{Msg.EMOJI_LOADING} <code>{duration}</code>')
        return "\n".join(parts)

    @staticmethod
    def user_mention(name: str, user_id: int) -> str:
        """Hyperlink mention (CatUserBot format.py pattern)."""
        return f"<a href='tg://user?id={user_id}'>{name}</a>"

    @staticmethod
    def code_block(text: str) -> str:
        """Inline code block (Moon/Dragon style)."""
        return f"<code>{text}</code>"

    @staticmethod
    def section(title: str, body: str, emoji: str = PIN) -> str:
        """
        Section header block.
        Uses Gothic (CatUserBot style) for the title.

             📌 𝕊𝕖𝕔𝕥𝕚𝕠𝕟 𝕋𝕚𝕥𝕝𝕖
             ├ body line 1
             └ body line 2
        """
        styled_title = font.double(title)
        return f"{emoji} <b>{styled_title}</b>\n{body}"


def plain_text(text: str) -> str:
    """Convert a formatted message (HTML/Markdown) to plain text suitable for
    contexts that don't support formatting (callback_answer, inline results).

    This is intentionally conservative: strip HTML tags, remove Markdown
    emphasis and code markers, unescape HTML entities, and normalize spaces
    while preserving newlines.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Remove HTML tags
    out = re.sub(r'<[^>]+>', '', text)

    # Remove common Markdown/markup chars that affect formatting
    out = re.sub(r'[\*`_~]', '', out)

    # Unescape HTML entities (e.g. &amp; → &)
    out = html.unescape(out)

    # Normalize spaces but preserve newlines
    out = '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in out.splitlines())
    return out.strip()
