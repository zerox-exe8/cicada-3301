"""
Kyro Discord Bot - Ultra-Realistic Red-Team Penetration Simulation (Components V2)
Simulates an authentic, high-severity cyber security audit and penetration breach
on a target member using real Discord identity forensics, realistic token structures,
deep system telemetry, and interactive Components V2 incident response controls.
"""

from __future__ import annotations

import asyncio
import base64
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
    """Persistent interactive post-breach incident response panel."""

    def __init__(self, target_name: str | None = None) -> None:
        super().__init__(timeout=None)
        self.target_name = target_name

    def _get_target(self, interaction: discord.Interaction) -> str:
        if self.target_name:
            return self.target_name
        msg = interaction.message
        if msg:
            import re
            m = re.search(r"User Identity:\s*<@!?(\d+)>", str(msg.content))
            if not m:
                for comp in getattr(msg, "components", []):
                    c_dict = getattr(comp, "to_dict", lambda: {})()
                    m = re.search(r"User Identity:\s*<@!?(\d+)>", str(c_dict))
                    if m:
                        break
            if m and interaction.guild:
                member = interaction.guild.get_member(int(m.group(1)))
                if member:
                    return member.display_name
        return "Target"

    @discord.ui.button(
        label="Terminate Session",
        style=discord.ButtonStyle.danger,
        custom_id="hack:terminate_session",
    )
    async def terminate_session(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Deliver realistic access denied security response."""
        target = self._get_target(interaction)
        resp = KyroContainer(accent_color=0xED4245)
        resp.add_section(
            content=(
                "**[SESSION TERMINATION FAILED] Access Denied**\n"
                "> Error `0x80070005`: Elevated Kernel Hook Detected.\n"
                f"> Target client `{target}` is currently locked in debug trace mode.\n\n"
                "> Relax! This was a 100% simulated penetration test."
            )
        )
        resp.add_separator(divider=True)
        resp.add_text("-# Kyro Red-Team Labs • Simulated Security Demonstration")
        await send_container_response(interaction, resp, ephemeral=True)

    @discord.ui.button(
        label="Decrypt Vault (ZIP)",
        style=discord.ButtonStyle.primary,
        custom_id="hack:decrypt_vault",
    )
    async def decrypt_vault(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Deliver encrypted archive security response."""
        target = self._get_target(interaction)
        resp = KyroContainer(accent_color=0x5865F2)
        resp.add_section(
            content=(
                "**[ENCRYPTION KEY REQUIRED] RSA-4096 Protected**\n"
                f"> Archive `{target.upper()}_EXFIL_DUMP.tar.gz` (1.82 GB) requires private key.\n"
                "> Audit Verified: No actual private user credentials were leaked or stored."
            )
        )
        resp.add_separator(divider=True)
        resp.add_text("-# Kyro Red-Team Labs • Simulated Security Demonstration")
        await send_container_response(interaction, resp, ephemeral=True)

    @discord.ui.button(
        label="Audit Certificate",
        style=discord.ButtonStyle.secondary,
        custom_id="hack:audit_cert",
    )
    async def audit_cert(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display verification disclaimer certificate."""
        target = self._get_target(interaction)
        case_id = random.randint(100000, 999999)
        resp = KyroContainer(accent_color=0x57F287)
        resp.add_section(
            content=(
                f"**Audit Certificate #SEC-{case_id}**\n"
                f"> Target: `{target}`\n"
                "> Classification: Harmless Entertainment Simulation\n"
                "> All tokens, passwords, and IPs generated for this command are synthetic."
            )
        )
        resp.add_separator(divider=True)
        resp.add_text("-# Kyro Red-Team Labs • Simulated Security Demonstration")
        await send_container_response(interaction, resp, ephemeral=True)


class HackCog(commands.Cog, name="Games-Hack"):
    """Hyper-realistic cyber penetration simulation engine built on Discord Components V2."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.bot.add_view(HackActionView())

    @commands.hybrid_command(
        name="hack",
        aliases=["fakehack", "trollhack", "audit"],
        description="Run a hyper-realistic cyber penetration test simulation on a member.",
    )
    @commands.guild_only()
    async def fake_hack(self, ctx: CustomContext, member: discord.Member) -> None:
        """Run an ultra-authentic penetration test audit simulation on a member."""
        # Bot defense protocol
        if member.id == self.bot.user.id:
            shield = KyroContainer(accent_color=0xED4245)
            shield.add_section(
                content=(
                    "**[SECURITY INCIDENT] Unauthorized Probing Detected**\n"
                    f"> Infiltration vector originated from {ctx.author.mention} (`{ctx.author.id}`).\n"
                    "> Kyro Hardware Security Module (HSM) deflected the incoming payload.\n"
                    "> Incident logged in Kyro Sentinel Threat Intelligence."
                ),
                accessory={
                    "type": 11,
                    "media": {"url": self.bot.user.display_avatar.url},
                },
            )
            shield.add_separator(divider=True)
            shield.add_text("-# Kyro Sentinel v4.9 • Hardware Security Module Protected")
            await send_container_response(ctx, shield)
            return

        # 1. Authentic Discord Token Construction (Real base64 user ID prefix)
        b64_uid = base64.b64encode(str(member.id).encode()).decode().rstrip("=")
        time_chars = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_", k=6))
        fake_token = f"{b64_uid}.{time_chars}.[REDACTED_BY_AUDIT]"

        # 2. Hardware and Client Platform Fingerprinting
        if member.is_on_mobile():
            os_name = "Android 14 (Linux 6.1.25-android14-9-g390d)"
            client_build = "Discord Mobile v224.12 (ARM64-v8a)"
        elif member.desktop_status != discord.Status.offline:
            os_name = "Windows 11 Pro 23H2 (Build 22631.3880 x64)"
            client_build = "Discord Stable 298.11 (Host 1.0.9146 / Electron 30.0.9)"
        elif member.web_status != discord.Status.offline:
            os_name = "Windows NT 10.0; Win64; x64"
            client_build = "Chrome/128.0.6613.120 (Discord Web Gateway v10)"
        else:
            os_name = "Windows NT 10.0; Win64; x64"
            client_build = "Discord Client Cache (Host 1.0.9146)"

        # 3. Process & Activity Inspection
        active_processes: list[str] = []
        if hasattr(member, "activities") and member.activities:
            for act in member.activities:
                if isinstance(act, discord.Spotify):
                    active_processes.append(f"Spotify.exe [Listening: \"{act.title}\" - {act.artist}]")
                elif isinstance(act, discord.Game):
                    active_processes.append(f"{act.name}.exe [DirectX 12 Hooked]")
                elif isinstance(act, discord.Streaming):
                    active_processes.append(f"OBS64.exe [Streaming: {act.platform}]")
                elif act.name:
                    active_processes.append(f"{act.name}.exe [PID {random.randint(4000, 9999)}]")
        if not active_processes:
            active_processes.append(f"Discord.exe (PID {random.randint(3000, 8500)}) [Main UI Thread]")
        primary_process = active_processes[0]

        # 4. Voice Channel Inspection
        if hasattr(member, "voice") and member.voice and member.voice.channel:
            vc = member.voice.channel
            voice_str = f"{vc.name} ({vc.bitrate // 1000}kbps Opus, RTC Active)"
        else:
            voice_str = "Inactive / Background RTC Listener Ready"

        # 5. Network & Geolocation Forensics
        fake_ip = f"{random.choice([103, 117, 182, 14, 49])}.{random.randint(10, 240)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
        fake_mac = f"4C:D5:77:{random.randint(16, 255):02X}:{random.randint(16, 255):02X}:{random.randint(16, 255):02X}"
        fake_isp = random.choice([
            "Jio Platforms Ltd / AS55836",
            "Bharti Airtel Ltd / AS45609",
            "Tata Communications / AS4755",
            "Vodafone Idea Ltd / AS55410",
        ])
        fake_loc = random.choice([
            "Mumbai (Maharashtra, IN)",
            "New Delhi (Delhi, IN)",
            "Bengaluru (Karnataka, IN)",
            "Hyderabad (Telangana, IN)",
            "Pune (Maharashtra, IN)",
        ])

        # 6. Realistic Passwords, Searches, and DMs
        passwords = [
            "iloveanime123",
            "discord2026!",
            "dont_hack_me_pls",
            "admin@1234",
            "qwertyuiop69",
            "naruto_is_real",
            "secretpassword420",
        ]
        fake_password = random.choice(passwords)

        searches = [
            "how to get free discord nitro 2026 without survey",
            "why do my friends ignore my general chat messages",
            "how to delete search history permanently before parents check",
            "how to look cool on discord voice channel",
            "cheap robux generator no virus 2026",
            "symptoms of being terminally online on discord",
        ]
        fake_search = random.choice(searches)

        secret_dms = [
            "bro please delete that embarrassing photo of me",
            "i swear i was just testing if nitro generators work",
            "can you lend me 5 dollars i'll pay you back next week",
            "dont tell the admins i pinged everyone by accident",
            "i secretly practice voice lines in empty voice channels",
        ]
        fake_dm = random.choice(secret_dms)

        clean_name = "".join(c for c in member.name.lower() if c.isalnum()) or "user"
        fake_email = f"{clean_name}{random.randint(11, 99)}@gmail.com"
        card_last4 = f"{random.randint(1000, 9999)}"
        pid = random.randint(3100, 8900)
        avatar_url = member.display_avatar.url

        # 4 Realistic Cyber-Audit Exploitation Phases
        phases = [
            {
                "pct": "25%",
                "bar": "[████████░░░░░░░░░░░░░░░░░░░░░░░░]",
                "title": "PHASE 01: RECONNAISSANCE & PORT EXPLOITATION",
                "logs": (
                    f"[*] Initiating stealth SYN port scan on {fake_ip}...\n"
                    f"[+] Port 22/tcp    (OpenSSH 8.9p1) .............. OPEN\n"
                    f"[+] Port 443/tcp   (Discord Gateway WSS TLS 1.3) . ESTABLISHED\n"
                    f"[+] Port 50001/udp (Discord RTC Voice Protocol) . ACTIVE\n"
                    f"[*] Remote OS Fingerprint: {os_name}\n"
                    f"[*] Injecting stage-1 exploit payload: cve_2026_discord_rce.dll (PID {pid})"
                ),
            },
            {
                "pct": "50%",
                "bar": "[████████████████░░░░░░░░░░░░░░░░]",
                "title": "PHASE 02: MEMORY INJECTION & LOCALSTORAGE HOOK",
                "logs": (
                    f"[*] Hooking Discord Electron process tree (PID {pid})...\n"
                    f"[+] Chromium sandbox escape verified: CVE-2026-31337\n"
                    f"[+] Memory pointer allocated: 0x7FFB9A100000 [PAGE_EXECUTE_READWRITE]\n"
                    f"[*] Dumping DPAPI Master Key from %APPDATA%\\discord...\n"
                    f"[+] DPAPI CryptUnprotectData: SUCCESS (Key: 0x9F7B4C2A)\n"
                    f"[+] LevelDB decrypted: Local Storage\\leveldb (Records: 1,420)"
                ),
            },
            {
                "pct": "75%",
                "bar": "[████████████████████████░░░░░░░░]",
                "title": "PHASE 03: TOKEN EXTRACTION & SESSION HIJACK",
                "logs": (
                    f"[*] Extracting LevelDB authorization tokens...\n"
                    f"[+] Discord Bearer Token intercepted:\n"
                    f"    --> {fake_token}\n"
                    f"[+] Authorization header verified against Discord API v10 [200 OK]\n"
                    f"[+] Account Email scraped: {fake_email}\n"
                    f"[*] Intercepting cached WebSocket telemetry packets..."
                ),
            },
            {
                "pct": "95%",
                "bar": "[██████████████████████████████░░]",
                "title": "PHASE 04: REAL-TIME TELEMETRY & SYSTEM EXFILTRATION",
                "logs": (
                    f"[+] Voice RTC Stream: {voice_str}\n"
                    f"[+] Active Application: {primary_process}\n"
                    f"[+] Dumping browser SQLite databases (Chrome/Edge/Brave)...\n"
                    f"[+] Intercepted unread DM buffer: \"{fake_dm}\"\n"
                    f"[+] Decrypted incognito search: \"{fake_search}\"\n"
                    f"[*] Compressing intelligence dossier: {clean_name}_breach.dossier"
                ),
            },
        ]

        # Stage 1 Dispatch
        p1 = phases[0]
        container = KyroContainer(accent_color=0xED4245)
        container.add_section(
            content=(
                f"**RED-TEAM PENETRATION AUDIT: `{member.display_name}`**\n"
                f"> Target ID: `{member.id}` • Status: `BREACHING ({p1['pct']})`"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}},
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**{p1['title']}**\n"
            f"```ini\n{p1['logs']}\n```\n"
            f"`Progress:` `{p1['bar']} {p1['pct']}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Kyro Red-Team Framework v4.9 • Target UID: {member.id}")

        msg = await send_container_response(ctx, container)

        # Loop through animation stages
        for p in phases[1:]:
            await asyncio.sleep(1.4)
            step_container = KyroContainer(accent_color=0xED4245)
            step_container.add_section(
                content=(
                    f"**RED-TEAM PENETRATION AUDIT: `{member.display_name}`**\n"
                    f"> Target ID: `{member.id}` • Status: `INFILTRATING ({p['pct']})`"
                ),
                accessory={"type": 11, "media": {"url": avatar_url}},
            )
            step_container.add_separator(divider=True)
            step_container.add_text(
                f"**{p['title']}**\n"
                f"```ini\n{p['logs']}\n```\n"
                f"`Progress:` `{p['bar']} {p['pct']}`"
            )
            step_container.add_separator(divider=True)
            step_container.add_text(f"-# Kyro Red-Team Framework v4.9 • Target UID: {member.id}")

            try:
                await edit_container_response(msg, step_container)
            except discord.HTTPException:
                break

        # Final Breach Report
        await asyncio.sleep(1.5)
        created_ts = int(member.created_at.timestamp())
        joined_ts = int(member.joined_at.timestamp()) if member.joined_at else created_ts
        is_admin = member.guild_permissions.administrator
        perm_str = "ROOT / ADMINISTRATOR" if is_admin else f"STANDARD USER (UID {member.id})"

        final_container = KyroContainer(accent_color=0xED4245)
        final_container.add_section(
            content=(
                f"**SECURITY INCIDENT REPORT: TARGET BREACH CONFIRMED**\n"
                f"> Target: {member.mention} • Threat Level: `CRITICAL (CVSS 9.8)` • Status: `ROOT ACCESS`"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}},
        )
        final_container.add_separator(divider=True)

        dossier = (
            f"**Target Identity & Hardware Fingerprint:**\n"
            f"> User Identity: {member.mention} (`{member.name}`)\n"
            f"> Account Age: Created <t:{created_ts}:R> • Joined <t:{joined_ts}:R>\n"
            f"> Operating System: `{os_name}`\n"
            f"> Client Build: `{client_build}`\n"
            f"> Privilege Level: `{perm_str}`\n\n"
            f"**Network Forensics & Geolocation:**\n"
            f"> Public IPv4: `{fake_ip}`\n"
            f"> MAC Address: `{fake_mac}`\n"
            f"> Geolocation Node: `{fake_loc}`\n"
            f"> Internet Service Provider: `{fake_isp}`\n"
            f"> Active Voice RTC: `{voice_str}`\n"
            f"> Active Process: `{primary_process}`\n\n"
            f"**Extracted Authentication Credentials:**\n"
            f"> Master Password: `{fake_password}`\n"
            f"> User Token: `{fake_token}`\n"
            f"> Registered Email: `{fake_email}`\n"
            f"> Linked Card: `4532 **** **** {card_last4} (Visa)`\n\n"
            f"**Intercepted Cache Records:**\n"
            f"> Private DM Snippet: `\"{fake_dm}\"`\n"
            f"> Recent Browser Query: `\"{fake_search}\"`"
        )
        final_container.add_text(dossier)
        final_container.add_separator(divider=True)
        final_container.add_text("-# Kyro Red-Team Framework v4.9 • For Authorized Security Demonstrations Only")

        view = HackActionView(target_name=member.display_name)
        try:
            await edit_container_response(msg, final_container, view=view)
        except discord.HTTPException:
            pass


async def setup(bot: KyroBot) -> None:
    bot.add_view(HackActionView())
    await bot.add_cog(HackCog(bot))
