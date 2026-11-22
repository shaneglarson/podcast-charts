"""Builds the daily HTML email report (inline styles so it renders in Gmail)."""
from datetime import datetime
from html import escape

ORANGE = "#E8590C"
INK = "#1d1d1f"
MUTED = "#6e6e73"
GREEN = "#1a7f37"
RED = "#cf222e"
LINE = "#e5e5ea"


def _when(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%b %-d at %-I:%M %p")
    except (TypeError, ValueError):
        return ""


def _prev_run(hist, today):
    earlier = [d for d in hist["runs"] if d < today]
    return earlier[-1] if earlier else None


def _ranks_on(series_by_country, date):
    out = {}
    for code, series in series_by_country.items():
        r = series.get(date)
        if r:
            out[code] = r
    return out


def _best_ever(series_by_country):
    best = {}
    for code, series in series_by_country.items():
        vals = [v for v in series.values() if v]
        if vals:
            best[code] = min(vals)
    return best


def _section(title, body):
    return (
        f'<h2 style="font:600 16px -apple-system,Segoe UI,Arial;color:{INK};margin:28px 0 10px;'
        f'padding-bottom:6px;border-bottom:2px solid {ORANGE}">{escape(title)}</h2>{body}'
    )


def _table(headers, rows):
    th = "".join(
        f'<th style="text-align:{"left" if i == 0 else "right"};font:600 12px Arial;color:{MUTED};'
        f'padding:6px 8px;border-bottom:1px solid {LINE}">{escape(h)}</th>'
        for i, h in enumerate(headers)
    )
    trs = ""
    for row in rows:
        tds = "".join(
            f'<td style="text-align:{"left" if i == 0 else "right"};font:14px Arial;color:{INK};'
            f'padding:6px 8px;border-bottom:1px solid {LINE}">{cell}</td>'
            for i, cell in enumerate(row)
        )
        trs += f"<tr>{tds}</tr>"
    return f'<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><tr>{th}</tr>{trs}</table>'


def _note(text):
    return f'<p style="font:14px Arial;color:{MUTED};margin:6px 0">{text}</p>'


def _move(diff):
    if diff > 0:
        return f'<span style="color:{GREEN};font-weight:600">▲ {diff}</span>'
    if diff < 0:
        return f'<span style="color:{RED};font-weight:600">▼ {abs(diff)}</span>'
    return f'<span style="color:{MUTED}">–</span>'


def build_report(hist, today, cfg, countries, flags):
    prev = _prev_run(hist, today)
    nice_date = datetime.strptime(today, "%Y-%m-%d").strftime("%a, %b %-d, %Y")
    name = lambda c: f"{flags.get(c, '')} {escape(countries.get(c, c.upper()))}"  # noqa: E731
    parts = []
    subject_bits = []

    for chart in cfg["charts"]:
        gid, cname = chart["genre_id"], chart["name"]
        series = hist["charts"].get(gid, {})
        now = _ranks_on(series, today)
        before = _ranks_on(series, prev) if prev else {}
        best = _best_ever(series)
        checked = hist.get("checked", {}).get(gid, {}).get(today, 0)

        new = sorted((c for c in now if c not in before), key=lambda c: now[c]) if prev else []
        dropped = sorted((c for c in before if c not in now), key=lambda c: before[c]) if prev else []
        moves = {c: before[c] - now[c] for c in now if c in before}

        # headline
        top = sorted(now.items(), key=lambda kv: kv[1])
        delta = f" ({len(now) - len(before):+d})" if prev else ""
        if top:
            subject_bits.append(f"#{top[0][1]} {countries.get(top[0][0], top[0][0]).split(' (')[0]} · {len(now)} countries{delta}")
        else:
            subject_bits.append(f"not charting today{delta}")

        stat = lambda label, val: (  # noqa: E731
            f'<td style="padding:12px;background:#fff7f2;border-radius:8px;text-align:center;width:33%">'
            f'<div style="font:700 26px Arial;color:{ORANGE}">{val}</div>'
            f'<div style="font:12px Arial;color:{MUTED}">{label}</div></td>'
        )
        best_today = f"#{top[0][1]}" if top else "—"
        parts.append(
            f'<h1 style="font:700 20px Arial;color:{INK};margin:24px 0 8px">Apple Podcasts · {escape(cname)} (Top {cfg.get("chart_limit", 200)})</h1>'
            f'<table cellpadding="0" cellspacing="6" style="width:100%"><tr>'
            f'{stat("countries charting", f"{len(now)}{delta}")}{stat("best rank today", best_today)}'
            f'{stat("storefronts checked", checked)}</tr></table>'
        )

        if not prev:
            parts.append(_note("First run — tomorrow's report will show movement, new entries and drop-outs."))

        if new:
            parts.append(_section(f"🆕 New countries ({len(new)})", _table(
                ["Country", "Rank", "Best ever"], [[name(c), f"#{now[c]}", f"#{best[c]}"] for c in new])))
        if dropped:
            parts.append(_section(f"⬇️ Dropped off the chart ({len(dropped)})", _table(
                ["Country", "Was", "Best ever"], [[name(c), f"#{before[c]}", f"#{best[c]}"] for c in dropped])))

        ups = sorted((c for c, d in moves.items() if d > 0), key=lambda c: -moves[c])[:10]
        downs = sorted((c for c, d in moves.items() if d < 0), key=lambda c: moves[c])[:10]
        if ups or downs:
            rows = [[name(c), f"#{before[c]} → #{now[c]}", _move(moves[c])] for c in ups + downs]
            parts.append(_section("📈 Biggest movers", _table(["Country", "Rank", "Change"], rows)))

        if top:
            rows = []
            for c, r in top:
                chg = _move(moves[c]) if c in moves else ('<span style="color:%s;font-weight:600">NEW</span>' % ORANGE if prev else "")
                rows.append([name(c), f"#{r}", chg, f"#{best[c]}"])
            parts.append(_section(f"🌍 Everywhere you're charting today ({len(top)})", _table(
                ["Country", "Rank", "Change", "Best ever"], rows)))
        else:
            parts.append(_section("🌍 Everywhere you're charting today", _note(
                f"Not in the Top {cfg.get('chart_limit', 200)} in any country today.")))

        pri = [c for c in cfg.get("priority_countries", []) if c in countries]
        if pri:
            rows = [[name(c), f"#{now[c]}" if c in now else "—", f"#{best[c]}" if c in best else "—"] for c in pri]
            parts.append(_section("⭐ Priority countries", _table(["Country", "Today", "Best ever"], rows)))

    # ratings
    ratings = hist.get("ratings", {})
    if cfg.get("track_ratings", True):
        now_r = {c: s[today] for c, s in ratings.items() if today in s}
        prev_r = {c: s[prev] for c, s in ratings.items() if prev and prev in s}
        total = sum(r["count"] for r in now_r.values())
        prev_total = sum(prev_r[c]["count"] for c in now_r if c in prev_r)
        cur_total_matched = sum(now_r[c]["count"] for c in now_r if c in prev_r)
        gained = cur_total_matched - prev_total if prev_r else None
        weighted = (sum(r["avg"] * r["count"] for r in now_r.values()) / total) if total else None
        head = f"{total:,} ratings across {len(now_r)} countries"
        if weighted:
            head += f" · {weighted:.2f}★ weighted average"
        if gained:
            head += f" · <b style='color:{GREEN}'>+{gained} since last report</b>"
        rows = []
        for c, r in sorted(now_r.items(), key=lambda kv: -kv[1]["count"]):
            d = r["count"] - prev_r[c]["count"] if c in prev_r else None
            rows.append([name(c), f"{r['avg']:.1f}★", f"{r['count']:,}",
                         _move(d).replace("▲ ", "+").replace("▼ ", "−") if d else ""])
        body = _note(head) + (_table(["Country", "Stars", "Ratings", "New"], rows) if rows else _note("No ratings found today."))
        parts.append(_section("⭐ Star ratings by country", body))
        if total:
            subject_bits.append(f"{weighted:.1f}★ ({total:,})")

    dash = cfg.get("dashboard_url")
    footer = (
        f'<p style="font:13px Arial;color:{MUTED};margin-top:28px">'
        + (f'<a href="{dash}" style="color:{ORANGE};font-weight:600">Open the full dashboard →</a><br>' if dash else "")
        + f"Checked {_when(hist.get('updated'))} Boise time. Source: Apple's public charts feed (Top {cfg.get('chart_limit', 200)}) and Apple Podcasts show pages.</p>"
    )
    html = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f5f5f7">'
        '<div style="max-width:640px;margin:0 auto;background:#fff;padding:24px 22px">'
        f'<div style="font:600 12px Arial;letter-spacing:.08em;text-transform:uppercase;color:{ORANGE}">'
        f'{escape(cfg["podcast_name"])} · Daily chart report</div>'
        f'<div style="font:14px Arial;color:{MUTED}">{nice_date}</div>'
        + "".join(parts) + footer + "</div></body></html>"
    )
    subject = f"🏀 {cfg['podcast_name']} charts {datetime.strptime(today, '%Y-%m-%d').strftime('%b %-d')}: " + " · ".join(subject_bits)
    return subject, html
