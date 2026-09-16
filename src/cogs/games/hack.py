"""
Kyro Discord Bot - Advanced Fake Hack Terminal Command (Components V2)
Simulates a hyper-realistic cyber infiltration terminal sequence trolling a target member.
Features live animated hacking phases, target profile intelligence, simulated data leaks,
and interactive Components V2 post-breach action buttons.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class HackActionView(discord.ui.View):
    """Interactive post-breach control panel buttons."""

    def __init__(self, target_name: str) -> None:
        super().__init__(timeout=180)
        self.target_name = target_name

    @discord.ui.button(
        label="Download Leaks (ZIP)",
        style=discord.ButtonStyle.primary,
        custom_id="hack:download_zip",
    )
    async def download_leaks(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Deliver funny encrypted archive warning to curious members."""
        troll = KyroContainer(accent_color=0xFF0055)
        troll.add_section(
            content=(
                "**[ACCESS DENIED] Encrypted Vault**\n"
                f"> Archive `{self.target_name.upper()}_LEAKS_2026.zip` (1.4 GB) is locked with AES-256.\n"
                "> Cyber Defense Division has logged your IP: `127.0.0.1`."
            )
        )
        troll.add_separator(divider=True)
        troll.add_text("-# 100% Fake Simulation • Kyro Cyber Threat Lab")
        await send_container_response(interaction, troll, ephemeral=True)

    @discord.ui.button(
        label="Nuke Client",
        style=discord.ButtonStyle.danger,
        custom_id="hack:nuke_client",
    )
    async def nuke_client(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Simulate sending a remote destructive packet to target's client."""
        troll = KyroContainer(accent_color=0xFF3300)
        troll.add_section(
            content=(
                f"**Remote Payload Dispatched to `{self.target_name}`**\n"
                "> Sent malicious instruction: `discord.exe --force-light-mode --volume 100`.\n"
                "> Client GPU cache corrupted. Target successfully blinded."
            )
        )
        troll.add_separator(divider=True)
        troll.add_text("-# 100% Fake Simulation • Kyro Cyber Threat Lab")
        await send_container_response(interaction, troll, ephemeral=True)

    @discord.ui.button(
        label="Report to FBI",
        style=discord.ButtonStyle.secondary,
        custom_id="hack:report_fbi",
    )
    async def report_fbi(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Trigger fake federal incident report ticket."""
        case_id = random.randint(100000, 999999)
        troll = KyroContainer(accent_color=0x3399FF)
        troll.add_section(
            content=(
                f"**Case #{case_id} Logged with Cyber Crimes Unit**\n"
                f"> Investigation opened into `{self.target_name}`'s suspicious incognito searches.\n"
                "> Federal agents have been dispatched to target coordinates."
            )
        )
        troll.add_separator(divider=True)
        troll.add_text("-# 100% Fake Simulation • Kyro Cyber Threat Lab")
        await send_container_response(interaction, troll, ephemeral=True)


class HackCog(commands.Cog, name="Games-Hack"):
    """Ultra-advanced fake hacker simulation suite built on Discord Components V2."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="hack",
        aliases=["fakehack", "trollhack"],
        description="Simulate a real-time cyber breach sequence on a target member.",
    )
    @commands.guild_only()
    async def fake_hack(self, ctx: CustomContext, member: discord.Member) -> None:
        """Run a simulated real-time terminal hacking sequence on a friend."""
        # Bot deflection defense
        if member.id == self.bot.user.id:
            shield = KyroContainer(accent_color=0x00FFCC)
            shield.add_section(
                content=(
                    "**[FIREWALL ACTIVE] Security Shield Engaged**\n"
                    "> Nice try! Kyro's quantum security core detected your infiltration attempt.\n"
                    "> Backdoor packet was reflected back to your terminal."
                ),
                accessory={
                    "type": 11,
                    "media": {"url": self.bot.user.display_avatar.url},
                },
            )
            shield.add_separator(divider=True)
            shield.add_text("-# Defense Protocol 0x88F • Kyro Security Core")
            await send_container_response(ctx, shield)
            return

        # Randomized realistic & hilarious breach variables
        passwords = [
            "iloveanime123",
            "password2026",
            "dont_hack_me_pls",
            "admin@1234",
            "catlover99",
            "qwertyuiop69",
            "supersecretnoob",
            "naruto_is_real",
            "sub_to_pewdiepie",
            "discordmod2026",
        ]
        fake_password = random.choice(passwords)

        fake_ip = f"{random.choice([103, 185, 192, 45])}.{random.randint(10, 240)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
        fake_token = f"mfa.{random.choice(['ODk', 'OTk', 'MTE', 'MTI'])}{random.randint(10000000, 99999999)}...[ENCRYPTED]"

        searches = [
            "how to get free discord nitro 2026 no human verification",
            "why do my friends ignore my general chat messages",
            "how to delete search history permanently before mom checks",
            "is it legal to marry an anime waifu in 2026",
            "how to look like a sigma on discord voice channel",
            "cheap robux generator without downloading virus",
            "symptoms of being terminally online on discord",
            "why does nobody reply to my hey in chat",
            "how to sound mysterious in voice chat",
        ]
        fake_search = random.choice(searches)

        secret_dms = [
            "bro please delete that photo of me with the cat ears",
            "i swear i was just testing if nitro generators work",
            "can you lend me 5 dollars i'll pay you back next month",
            "dont tell the admins i pinged everyone by accident",
            "i secretly practice voice lines in empty voice channels",
            "pls tell me im cool i bought discord nitro for a month",
        ]
        fake_dm = random.choice(secret_dms)

        cities = ["Mumbai, IN", "Delhi, IN", "Bengaluru, IN", "Frankfurt, DE", "Tokyo, JP", "London, UK", "Ashburn, US"]
        fake_location = random.choice(cities)
        isps = ["Jio Fiber Hypernode", "Airtel Xstream Giga", "Cloudflare Warp Route", "Starlink Orbital Net"]
        fake_isp = random.choice(isps)

        clean_name = "".join(c for c in member.name.lower() if c.isalnum()) or "user"
        fake_email = f"{clean_name}{random.randint(11, 99)}@gmail.com"
        fake_card = f"4532 **** **** {random.randint(1000, 9999)} (Visa - Exp: 09/28)"

        # Device detection
        if member.is_on_mobile():
            device_str = "Discord Mobile (Android/iOS)"
        elif member.desktop_status != discord.Status.offline:
            device_str = "Discord Desktop (Windows/macOS)"
        else:
            device_str = "Discord Web Gateway"

        avatar_url = member.display_avatar.url
        pid = random.randint(3100, 9800)

        # 5 Terminal infiltration stages
        stages_data = [
            {
                "pct": "20%",
                "bar": "[■■□□□□□□□□]",
                "phase": "Phase 1: Gateway Reconnaissance & Port Exploitation",
                "logs": (
                    f"> [INIT] Initializing Kali Cyber-Scan v6.4 -> Target: {member.name}\n"
                    f"> [PROBE] Gateway established with IP {fake_ip}\n"
                    f"> [PORTS] Port 22 (SSH), 443 (SSL/TLS), 8080 (Proxy) ... [OPEN]\n"
                    f"> [INJECT] Zero-day DLL payload injected into Discord.exe (PID {pid})"
                ),
            },
            {
                "pct": "40%",
                "bar": "[■■■■□□□□□□]",
                "phase": "Phase 2: Security Subversion & Password Extraction",
                "logs": (
                    f"> [DUMP] Reading active process V8 memory buffers at 0x7FFF00A1...\n"
                    f"> [BYPASS] Discord 2FA TOTP authenticator successfully bypassed\n"
                    f"> [CRACK] Bruteforcing master hash via John the Ripper (rockyou.txt)...\n"
                    f"> [MATCH] Master credentials matched: \"{fake_password}\""
                ),
            },
            {
                "pct": "60%",
                "bar": "[■■■■■■□□□□]",
                "phase": "Phase 3: Session Hijack & Network Node Triangulation",
                "logs": (
                    f"> [WEBSOCKET] Sniffing Discord Gateway v10 communication stream...\n"
                    f"> [SCRAPE] Authorization bearer token captured: \"{fake_token}\"\n"
                    f"> [LOCATE] Node coordinates resolved: {fake_location}\n"
                    f"> [CARRIER] Intercepted link carrier: {fake_isp} (Latency: {random.randint(12, 45)}ms)"
                ),
            },
            {
                "pct": "80%",
                "bar": "[■■■■■■■■□□]",
                "phase": "Phase 4: SQLite Database Mining & Secret DMs Exfiltration",
                "logs": (
                    f"> [MINING] Decrypting local Chrome & Discord SQLite databases...\n"
                    f"> [HISTORY] Decrypted incognito search: \"{fake_search}\"\n"
                    f"> [SNIFF] Mining unread direct messages and unsaved media...\n"
                    f"> [LEAK] Intercepted private draft: \"{fake_dm}\""
                ),
            },
        ]

        # Stage 1 Dispatch
        s1 = stages_data[0]
        container = KyroContainer(accent_color=0x00FF66)
        container.add_section(
            content=(
                f"**Terminal Infiltration: `{member.display_name}`**\n"
                f"> Status: `BREACHING ({s1['pct']})` • Gateway: `CONNECTED`"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}},
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**{s1['phase']}**\n"
            f"```ini\n{s1['logs']}\n```\n"
            f"`Progress:` `{s1['bar']} {s1['pct']}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Kyro Cyber Threat Engine v4.2 • Target ID: {member.id}")

        msg = await send_container_response(ctx, container)

        # Loop through animation stages
        for s in stages_data[1:]:
            await asyncio.sleep(1.4)
            step_container = KyroContainer(accent_color=0x00FF66)
            step_container.add_section(
                content=(
                    f"**Terminal Infiltration: `{member.display_name}`**\n"
                    f"> Status: `INFILTRATING ({s['pct']})` • Gateway: `CONNECTED`"
                ),
                accessory={"type": 11, "media": {"url": avatar_url}},
            )
            step_container.add_separator(divider=True)
            step_container.add_text(
                f"**{s['phase']}**\n"
                f"```ini\n{s['logs']}\n```\n"
                f"`Progress:` `{s['bar']} {s['pct']}`"
            )
            step_container.add_separator(divider=True)
            step_container.add_text(f"-# Kyro Cyber Threat Engine v4.2 • Target ID: {member.id}")

            try:
                await edit_container_response(msg, step_container)
            except discord.HTTPException:
                break

        # Final Stage: Complete Compromise
        await asyncio.sleep(1.4)
        created_ts = int(member.created_at.timestamp())
        joined_ts = int(member.joined_at.timestamp()) if member.joined_at else created_ts

        final_container = KyroContainer(accent_color=0x00FF66)
        final_container.add_section(
            content=(
                f"**Terminal Breach Complete: `{member.display_name}` Owned**\n"
                f"> Access Level: `ROOT ACCESS GRANTED` • Exfiltration: `100% COMPLETE`"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}},
        )
        final_container.add_separator(divider=True)

        breach_summary = (
            f"**Target System Intelligence:**\n"
            f"> Target: {member.mention} (`{member.name}`)\n"
            f"> Account Age: Created <t:{created_ts}:R> • Joined <t:{joined_ts}:R>\n"
            f"> Client Device: `{device_str}`\n"
            f"> Highest Role: {member.top_role.mention if member.top_role else '@everyone'}\n\n"
            f"**Exfiltrated Credentials & Network Data:**\n"
            f"> Master Password: `{fake_password}`\n"
            f"> IP Address: `{fake_ip}` ({fake_location})\n"
            f"> Gateway Token: `{fake_token}`\n"
            f"> Linked Email: `{fake_email}`\n"
            f"> Billing Card: `{fake_card}`\n\n"
            f"**Intercepted Private Communications:**\n"
            f"> Recent Incognito Search: `\"{fake_search}\"`\n"
            f"> Leaked Secret DM: `\"{fake_dm}\"`"
        )
        final_container.add_text(breach_summary)
        final_container.add_separator(divider=True)
        final_container.add_text("-# 100% Fake Simulation • Powered by Kyro Studio")

        view = HackActionView(target_name=member.display_name)
        try:
            await edit_container_response(msg, final_container, view=view)
        except discord.HTTPException:
            pass


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(HackCog(bot))
