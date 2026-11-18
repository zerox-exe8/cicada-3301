---
name: kyro-discord-patterns
description: Discord.py and Kyro UI/concurrency patterns skill. Use when authoring Components V2 cards, handling custom emojis, voice locking, or asynchronous tasks.
---

# Kyro Discord Patterns Skill

Guidelines and code patterns for developing robust, beautifully formatted Discord interactions in Kyro.

## 1. Components V2 & KyroContainer
- Always build UI with `KyroContainer`:
  ```python
  from src.utils.containers import KyroContainer, send_container_response

  container = KyroContainer(accent_color=None)
  container.add_section(
      content="**Header Title**\n> Detailed body description.",
      accessory={"type": 11, "media": {"url": image_url}} if image_url else None,
  )
  container.add_separator(divider=True)
  container.add_text(f"-# Requested by {ctx.author.display_name}")
  await send_container_response(ctx, container)
  ```
- Protect Markdown URLs: Replace square brackets in song/video titles (`[` -> `(`, `]` -> `)`) before embedding in links: `[{safe_title}]({url})`.

## 2. Custom Application Emojis
- Retrieve custom Kyro application emojis via `bot.custom_emojis.get("<name>")` or `bot.custom_emojis.get_emoji_obj("<name>")`.
- Never substitute raw unicode emojis where a Kyro custom emoji is designated.

## 3. Concurrency & Voice Locking
- Serialize all voice joins/moves with `GuildPlayer._connect_lock`:
  ```python
  async with player._connect_lock:
      await player.connect_voice(channel)
  ```
- Serialize track advancing with `GuildPlayer._advance_lock`:
  ```python
  async with player._advance_lock:
      await player.advance_track()
  ```

## 4. Tracked Background Tasks
- Never call raw `asyncio.create_task(...)` for fire-and-forget tasks.
- Always use `create_tracked_task(coro, name=...)` from `src.utils.tasks`.

## 5. Resilient Error Handling
- Never use bare `except: pass` or `except Exception: pass`.
- For best-effort message deletions:
  ```python
  except (discord.NotFound, discord.Forbidden):
      pass  # message already deleted or missing permission
  ```
- For background task failures, log with `logger.debug` or `logger.warning(..., exc_info=True)`.
