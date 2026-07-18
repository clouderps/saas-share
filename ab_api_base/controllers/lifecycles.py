# -*- coding: utf-8 -*-
"""Served API lifecycle guide — /api/v1/lifecycles.

The flat Swagger reference lists *which* endpoints exist; this page shows the
*order* to call them — the real client journeys (portal, POS, dashboard) as
numbered call sequences with example request/response. Zero external deps:
the sequence overviews are pure CSS (no diagram library), matching the
offline-first philosophy of the vendored Swagger UI + inline-SVG guide.

Installed on both servers via ab_api_base, so the same journey guide is
reachable at /api/v1/lifecycles on tenant and central alike. Gated by the
same ab_api.expose_docs switch as the rest of the docs.
"""

from odoo import http, SUPERUSER_ID
from odoo.http import request, Response

from .docs import _docs_enabled


class ApiLifecyclesController(http.Controller):

    @http.route('/api/v1/lifecycles', type='http', auth='public', csrf=False)
    def lifecycles(self, **kwargs):
        env = request.env(user=SUPERUSER_ID)
        if not _docs_enabled(env):
            return Response('Not found', status=404)
        return Response(_LIFECYCLES_HTML, headers=[('Content-Type', 'text/html; charset=utf-8')])


_LIFECYCLES_HTML = """<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Ghaima API - Lifecycles</title>
<style>
  :root{
    --bg:#F7F8FC;--surface:#FFFFFF;--surface-2:#EEF2FB;
    --ink:#0A1B3D;--ink-soft:#4A5876;--ink-faint:#7C88A6;--line:#E2E7F1;
    --tenant:#005FF6;--tenant-bg:#E7F0FF;--central:#0E9F8E;--central-bg:#DBF5F0;
    --ok:#0E8F5E;--ok-bg:#DEF5EA;--warn:#B45309;--warn-bg:#FBECD6;--err:#C2185B;--err-bg:#FBE1EC;
    --code-bg:#0C1430;--code-ink:#D7E0F5;--code-line:#22315C;
    --radius:14px;--radius-sm:9px;
    --shadow:0 1px 2px rgba(13,0,80,.04),0 8px 24px -12px rgba(13,0,80,.18);
    --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,Consolas,monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  }
  @media (prefers-color-scheme:dark){:root{
    --bg:#080D1C;--surface:#0F1830;--surface-2:#152241;--ink:#EAF0FF;--ink-soft:#A6B4D6;--ink-faint:#6E7EA6;--line:#213151;
    --tenant:#4C8DFF;--tenant-bg:#132449;--central:#33C9B7;--central-bg:#0E2E2C;
    --ok:#3FD08A;--ok-bg:#0E2C22;--warn:#E0A24B;--warn-bg:#33260F;--err:#F06A9B;--err-bg:#341021;
    --code-bg:#070C1C;--code-ink:#CBD6F0;--code-line:#1B2A4E;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.7);}}
  :root[data-theme="dark"]{
    --bg:#080D1C;--surface:#0F1830;--surface-2:#152241;--ink:#EAF0FF;--ink-soft:#A6B4D6;--ink-faint:#6E7EA6;--line:#213151;
    --tenant:#4C8DFF;--tenant-bg:#132449;--central:#33C9B7;--central-bg:#0E2E2C;
    --ok:#3FD08A;--ok-bg:#0E2C22;--warn:#E0A24B;--warn-bg:#33260F;--err:#F06A9B;--err-bg:#341021;
    --code-bg:#070C1C;--code-ink:#CBD6F0;--code-line:#1B2A4E;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.7);}
  :root[data-theme="light"]{
    --bg:#F7F8FC;--surface:#FFFFFF;--surface-2:#EEF2FB;--ink:#0A1B3D;--ink-soft:#4A5876;--ink-faint:#7C88A6;--line:#E2E7F1;
    --tenant:#005FF6;--tenant-bg:#E7F0FF;--central:#0E9F8E;--central-bg:#DBF5F0;
    --ok:#0E8F5E;--ok-bg:#DEF5EA;--warn:#B45309;--warn-bg:#FBECD6;--err:#C2185B;--err-bg:#FBE1EC;
    --code-bg:#0C1430;--code-ink:#D7E0F5;--code-line:#22315C;
    --shadow:0 1px 2px rgba(13,0,80,.04),0 8px 24px -12px rgba(13,0,80,.18);}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6;font-size:16px;-webkit-font-smoothing:antialiased;}
  .wrap{max-width:1120px;margin:0 auto;padding:0 24px;}
  header.top{border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--surface),var(--bg));position:relative;}
  header.top .wrap{padding:54px 24px 40px;}
  .kicker{font:600 12px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--central);display:flex;align-items:center;gap:9px;margin-bottom:20px;}
  .kicker .dot{width:7px;height:7px;border-radius:50%;background:var(--central);box-shadow:0 0 0 4px var(--central-bg);}
  h1{font-size:clamp(30px,5vw,46px);line-height:1.04;margin:0 0 16px;letter-spacing:-.02em;text-wrap:balance;font-weight:800;}
  h1 .accent{color:var(--tenant);}
  .lede{font-size:clamp(16px,2vw,19px);color:var(--ink-soft);max-width:62ch;margin:0;}
  .lede b{color:var(--ink);font-weight:650;}
  .legend{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px;}
  .srv{display:inline-flex;align-items:center;gap:9px;padding:9px 14px;border:1px solid var(--line);border-radius:999px;background:var(--surface);font:600 13px/1 var(--sans);box-shadow:var(--shadow);}
  .srv .sw{width:11px;height:11px;border-radius:3px;}.srv .host{font:500 12px/1 var(--mono);color:var(--ink-faint);}
  .sw.t{background:var(--tenant);}.sw.c{background:var(--central);}
  .theme-toggle{position:absolute;top:20px;inset-inline-end:24px;width:38px;height:38px;border-radius:10px;border:1px solid var(--line);background:var(--surface);color:var(--ink);font-size:17px;cursor:pointer;box-shadow:var(--shadow);}
  .theme-toggle:focus-visible{outline:2px solid var(--tenant);outline-offset:2px;}
  .cols{display:grid;grid-template-columns:1fr;gap:48px;padding:52px 0 80px;}
  @media (min-width:940px){.cols{grid-template-columns:200px 1fr;gap:56px;}}
  nav.side{align-self:start;}
  @media (min-width:940px){nav.side{position:sticky;top:28px;}}
  nav.side ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px;}
  nav.side a{display:flex;gap:11px;align-items:baseline;padding:9px 12px;border-radius:var(--radius-sm);color:var(--ink-soft);text-decoration:none;font-size:14.5px;font-weight:550;border:1px solid transparent;}
  nav.side a:hover{background:var(--surface-2);color:var(--ink);}
  nav.side a .n{font:700 12px/1 var(--mono);color:var(--ink-faint);min-width:16px;}
  nav.side .grp{font:600 11px/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ink-faint);padding:16px 12px 7px;}
  main{min-width:0;}
  section.journey{scroll-margin-top:24px;margin-bottom:64px;}
  .j-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:8px;}
  .j-num{flex:none;width:40px;height:40px;border-radius:11px;display:grid;place-items:center;font:800 17px/1 var(--mono);color:#fff;}
  .j-num.t{background:var(--tenant);}.j-num.c{background:var(--central);}
  .j-head h2{font-size:24px;margin:2px 0 4px;letter-spacing:-.015em;}
  .j-head p{margin:0;color:var(--ink-soft);font-size:15px;}
  .server-tag{font:600 10.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;padding:4px 8px;border-radius:6px;vertical-align:middle;margin-inline-start:8px;}
  .server-tag.t{color:var(--tenant);background:var(--tenant-bg);}.server-tag.c{color:var(--central);background:var(--central-bg);}
  .flow{display:flex;align-items:center;gap:8px;margin:20px 0 26px;padding:16px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow-x:auto;box-shadow:var(--shadow);}
  .fnode{flex:none;display:flex;flex-direction:column;gap:6px;padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--surface-2);}
  .fnode .fn{font:800 11px/1 var(--mono);color:var(--ink-faint);}
  .fnode .frow{display:flex;align-items:center;gap:7px;}
  .fnode code{font:600 12px/1.3 var(--mono);color:var(--ink);white-space:nowrap;}
  .farrow{flex:none;color:var(--ink-faint);font-size:18px;}
  .fcap{flex:none;font:700 11px/1.3 var(--mono);color:var(--ink-faint);text-transform:uppercase;letter-spacing:.06em;text-align:center;white-space:nowrap;}
  .steps{display:flex;flex-direction:column;gap:14px;}
  .step{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:hidden;}
  .step>.bar{display:flex;align-items:center;gap:11px;flex-wrap:wrap;padding:13px 16px;border-bottom:1px solid var(--line);background:var(--surface-2);}
  .step .sn{font:800 12px/1 var(--mono);color:var(--ink-faint);}
  .method{font:700 11px/1 var(--mono);letter-spacing:.05em;padding:5px 8px;border-radius:6px;color:#fff;}
  .method.get{background:var(--central);}.method.post{background:var(--tenant);}
  .path{font:600 13.5px/1.4 var(--mono);color:var(--ink);word-break:break-all;}
  .step .desc{margin-inline-start:auto;font-size:13px;color:var(--ink-soft);}
  .step .body{padding:15px 16px;display:grid;gap:14px;}
  @media (min-width:680px){.step .body.pair{grid-template-columns:1fr 1fr;}}
  .io-label{font:600 10.5px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--ink-faint);margin-bottom:7px;display:flex;align-items:center;gap:7px;}
  .io-label .pip{width:6px;height:6px;border-radius:50%;}.pip.req{background:var(--ink-faint);}.pip.res{background:var(--ok);}
  pre.code{margin:0;background:var(--code-bg);color:var(--code-ink);border:1px solid var(--code-line);border-radius:var(--radius-sm);padding:13px 14px;overflow-x:auto;font:500 12.5px/1.65 var(--mono);tab-size:2;}
  pre.code .k{color:#7FA6FF;}pre.code .s{color:#5DD8CA;}pre.code .n{color:#F0A35E;}pre.code .b{color:#C08CFF;}pre.code .c{color:var(--ink-faint);font-style:italic;}
  .status{font:700 11px/1 var(--mono);padding:4px 8px;border-radius:6px;}
  .status.ok{color:var(--ok);background:var(--ok-bg);}.status.warn{color:var(--warn);background:var(--warn-bg);}.status.err{color:var(--err);background:var(--err-bg);}
  .note{display:flex;gap:12px;padding:14px 16px;border-radius:var(--radius-sm);background:var(--warn-bg);border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);font-size:14px;color:var(--ink);margin-top:14px;}
  .note .ic{color:var(--warn);font-weight:800;flex:none;font-family:var(--mono);}
  .note.info{background:var(--central-bg);border-color:color-mix(in srgb,var(--central) 30%,transparent);}.note.info .ic{color:var(--central);}
  .ref{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);overflow:auto;}
  table{width:100%;border-collapse:collapse;font-size:13.5px;}
  th,td{text-align:start;padding:11px 18px;border-top:1px solid var(--line);vertical-align:top;}
  th{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-faint);}
  td .mono{font:500 12.5px/1.5 var(--mono);}
  .no{color:var(--err);font-weight:800;}
  footer{border-top:1px solid var(--line);color:var(--ink-soft);font-size:13.5px;padding:28px 0 60px;}
  footer .wrap{display:flex;flex-wrap:wrap;gap:8px 20px;justify-content:space-between;}
  footer code{font-family:var(--mono);color:var(--ink);}
  footer a{color:var(--tenant);}
</style>
</head>
<body>
<header class="top">
  <button id="tt" class="theme-toggle" aria-label="Toggle light/dark theme" title="Toggle theme">&#9680;</button>
  <div class="wrap">
    <div class="kicker"><span class="dot"></span>Ghaima Platform &middot; API Field Guide</div>
    <h1>How the API is actually <span class="accent">used</span>, not just listed.</h1>
    <p class="lede">Swagger tells you <b>which</b> endpoints exist. It never tells you the <b>order</b> to call them. This guide walks the real client journeys &mdash; <b>log in &rarr; see your instances &rarr; open one &rarr; read its dashboard</b> &mdash; as call sequences, with the exact request and the exact response captured from a live run.</p>
    <div class="legend">
      <span class="srv"><span class="sw t"></span>Tenant API <span class="host">POS / store</span></span>
      <span class="srv"><span class="sw c"></span>Central API <span class="host">Customer Portal</span></span>
    </div>
  </div>
</header>
<div class="wrap"><div class="cols">
  <nav class="side" aria-label="Journeys">
    <div class="grp">Journeys</div>
    <ol>
      <li><a href="#portal"><span class="n">01</span>Customer Portal</a></li>
      <li><a href="#pos"><span class="n">02</span>POS Shift &amp; Sale</a></li>
      <li><a href="#dash"><span class="n">03</span>Owner Dashboard</a></li>
    </ol>
    <div class="grp">Reference</div>
    <ol>
      <li><a href="#tokens"><span class="n">&middot;</span>Tokens &amp; scope</a></li>
      <li><a href="/api/v1/docs"><span class="n">&#8599;</span>Swagger</a></li>
    </ol>
  </nav>
  <main>
    <section class="journey" id="portal">
      <div class="j-head"><div class="j-num c">01</div><div>
        <h2>Customer Portal <span class="server-tag c">Central &middot; Portal</span></h2>
        <p>A tenant owner signs in, sees every Odoo instance they own with live KPIs, drills into one, and opens it with a one-time secure login. Every payload below is real output from a live trace.</p>
      </div></div>
      <div class="flow" role="list" aria-label="Call sequence">
        <span class="fcap">App</span><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">01</span><div class="frow"><span class="method post">POST</span><code>/saas/auth/login</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">02</span><div class="frow"><span class="method get">GET</span><code>/me/tenants</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">03</span><div class="frow"><span class="method get">GET</span><code>/me/dashboard/aggregate</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">04</span><div class="frow"><span class="method get">GET</span><code>/me/tenants/9/*</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">05</span><div class="frow"><span class="method post">POST</span><code>/me/tenants/9/access</code></div></div><span class="farrow">&rarr;</span>
        <span class="fcap">Odoo&nbsp;opens</span>
      </div>
      <div class="steps">
        <article class="step">
          <div class="bar"><span class="sn">01</span><span class="method post">POST</span><span class="path">/api/v1/saas/auth/login</span><span class="desc">exchange credentials for a token</span></div>
          <div class="body pair">
            <div><div class="io-label"><span class="pip req"></span>Request</div>
<pre class="code"><span class="b">{</span>
  <span class="k">"login"</span>: <span class="s">"owner@company.sa"</span>,
  <span class="k">"password"</span>: <span class="s">"&bull;&bull;&bull;&bull;&bull;&bull;"</span>,
  <span class="k">"device_uid"</span>: <span class="s">"ios-4F9A"</span>
<span class="b">}</span></pre></div>
            <div><div class="io-label"><span class="pip res"></span>Response <span class="status ok">200</span></div>
<pre class="code"><span class="b">{</span> <span class="k">"success"</span>:<span class="n">true</span>, <span class="k">"data"</span>:<span class="b">{</span>
  <span class="k">"access_token"</span>:<span class="s">"eyJhbGci..."</span>,
  <span class="k">"refresh_token"</span>:<span class="s">"..."</span>,
  <span class="k">"expires_in"</span>:<span class="n">3600</span>,
  <span class="k">"partner_id"</span>:<span class="n">17</span>,
  <span class="k">"name"</span>:<span class="s">"Company Admin"</span>
<span class="b">}}</span></pre></div>
          </div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">02</span><span class="method get">GET</span><span class="path">/api/v1/saas/me/tenants</span><span class="desc">the multi-instance list &mdash; with KPIs baked in</span></div>
          <div class="body">
            <div><div class="io-label"><span class="pip res"></span>Response <span class="status ok">200</span> &middot; one card per instance</div>
<pre class="code"><span class="b">{</span> <span class="k">"success"</span>:<span class="n">true</span>, <span class="k">"data"</span>:<span class="b">{</span>
  <span class="k">"period"</span>:<span class="s">"today"</span>,
  <span class="k">"tenants"</span>:<span class="b">[</span> <span class="b">{</span>
    <span class="k">"subscription_id"</span>:<span class="n">9</span>,          <span class="c">// use this id for every drill-in below</span>
    <span class="k">"name"</span>:<span class="s">"SUB-00004"</span>, <span class="k">"state"</span>:<span class="s">"done"</span>,
    <span class="k">"fqdn"</span>:<span class="s">"fayiaprod.saas.local"</span>,
    <span class="k">"odoo_url"</span>:<span class="s">"https://fayiaprod.saas.local"</span>,
    <span class="k">"kpi_revenue_total"</span>:<span class="n">1234.5</span>, <span class="k">"kpi_revenue_currency"</span>:<span class="s">"SAR"</span>,
    <span class="k">"kpi_orders_count"</span>:<span class="n">7</span>, <span class="k">"kpi_sessions_open"</span>:<span class="n">1</span>,
    <span class="k">"kpi_devices_online"</span>:<span class="n">2</span>, <span class="k">"kpi_is_stale"</span>:<span class="n">true</span>
  <span class="b">}</span> <span class="b">]</span>
<span class="b">}}</span></pre></div>
            <div class="note info"><span class="ic">i</span><div>The list already carries each instance's headline KPIs, so the home screen renders with <b>one</b> call &mdash; no fan-out per instance. <span class="path">kpi_is_stale:true</span> means the snapshot cron hasn't refreshed recently; show an "updated 2h ago" hint, not a spinner.</div></div>
          </div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">03</span><span class="method get">GET</span><span class="path">/api/v1/saas/me/dashboard/aggregate</span><span class="desc">totals across every instance</span></div>
          <div class="body"><div><div class="io-label"><span class="pip res"></span>Response <span class="status ok">200</span></div>
<pre class="code"><span class="b">{</span> <span class="k">"data"</span>:<span class="b">{</span>
  <span class="k">"tenant_count"</span>:<span class="n">1</span>, <span class="k">"covered_tenants"</span>:<span class="n">1</span>, <span class="k">"stale_tenants"</span>:<span class="n">1</span>,
  <span class="k">"revenue_total"</span>:<span class="n">1234.5</span>, <span class="k">"revenue_currency"</span>:<span class="s">"SAR"</span>,
  <span class="k">"orders_count"</span>:<span class="n">7</span>, <span class="k">"sessions_open"</span>:<span class="n">1</span>, <span class="k">"sessions_total"</span>:<span class="n">3</span>,
  <span class="k">"devices_online"</span>:<span class="n">2</span>, <span class="k">"last_captured_at"</span>:<span class="s">"2026-07-02T06:49:54"</span>
<span class="b">}}</span></pre></div></div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">04</span><span class="method get">GET</span><span class="path">/api/v1/saas/me/tenants/9/{detail &middot; resources &middot; users &middot; apps}</span><span class="desc">four reads build the instance screen</span></div>
          <div class="body pair">
            <div><div class="io-label"><span class="pip res"></span>/detail + /resources</div>
<pre class="code"><span class="c">// /detail</span>
<span class="b">{</span> <span class="k">"entity_id"</span>:<span class="n">4</span>, <span class="k">"name"</span>:<span class="s">"fayiaprod"</span>,
  <span class="k">"state"</span>:<span class="s">"launched"</span>, <span class="k">"version"</span>:<span class="s">"18.0"</span>,
  <span class="k">"user_count"</span>:<span class="n">1</span> <span class="b">}</span>
<span class="c">// /resources</span>
<span class="b">{</span> <span class="k">"cpu_usage_percent"</span>:<span class="n">0.0</span>,
  <span class="k">"memory_usage_percent"</span>:<span class="n">0.0</span>,
  <span class="k">"disk_usage_percent"</span>:<span class="n">0.0</span> <span class="b">}</span></pre></div>
            <div><div class="io-label"><span class="pip res"></span>/users + /apps</div>
<pre class="code"><span class="c">// /users</span>
<span class="b">{</span> <span class="k">"users"</span>:<span class="b">[</span><span class="b">{</span> <span class="k">"name"</span>:<span class="s">"Company Admin"</span>,
   <span class="k">"role"</span>:<span class="s">"admin"</span>, <span class="k">"state"</span>:<span class="s">"active"</span> <span class="b">}]</span> <span class="b">}</span>
<span class="c">// /apps</span>
<span class="b">{</span> <span class="k">"apps"</span>:<span class="b">{</span> <span class="k">"pos"</span>:<span class="n">true</span>, <span class="k">"kitchen"</span>:<span class="n">true</span>,
   <span class="k">"dashboard"</span>:<span class="n">true</span>, <span class="k">"shift_management"</span>:<span class="n">false</span> <span class="b">}</span>,
  <span class="k">"max_devices"</span>:<span class="n">5</span>, <span class="k">"active_devices"</span>:<span class="n">2</span> <span class="b">}</span></pre></div>
          </div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">05</span><span class="method post">POST</span><span class="path">/api/v1/saas/me/tenants/9/access</span><span class="desc">open the instance &mdash; one-time secure login</span></div>
          <div class="body pair">
            <div><div class="io-label"><span class="pip req"></span>Request</div>
<pre class="code"><span class="b">{</span> <span class="k">"device_uid"</span>: <span class="s">"ios-4F9A"</span> <span class="b">}</span>
<span class="c">// required - binds the grant
// to this physical device</span></pre></div>
            <div><div class="io-label"><span class="pip res"></span>Response &middot; secure hand-off</div>
<pre class="code"><span class="b">{</span> <span class="k">"data"</span>:<span class="b">{</span>
  <span class="k">"login_url"</span>:<span class="s">"https://fayiaprod.../..."</span>,
  <span class="k">"expires_in"</span>:<span class="n">60</span> <span class="b">}}</span></pre></div>
          </div>
          <div style="padding:0 16px 16px">
          <div class="note"><span class="ic">!</span><div><b>This step crosses servers.</b> Central calls the tenant's <span class="path">/api/v1/ghaima/device-auth</span> to mint the grant. Requires <span class="path">ab_ghaima_client_verify</span> on the tenant and a freshly-booted tenant server (routes register at startup) &mdash; otherwise it returns <span class="status err">502 TENANT_AUTH_FAILED</span>.</div></div>
          </div>
        </article>
      </div>
    </section>

    <section class="journey" id="pos">
      <div class="j-head"><div class="j-num t">02</div><div>
        <h2>POS Shift &amp; Sale <span class="server-tag t">Tenant &middot; Store</span></h2>
        <p>A cashier authenticates on a store device, opens a session, rings a sale, and closes out. Runs entirely on the tenant server; the token is scoped to that device + branch and sees only the current cashier's data.</p>
      </div></div>
      <div class="flow" role="list" aria-label="Call sequence">
        <span class="fcap">Till</span><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">01</span><div class="frow"><span class="method post">POST</span><code>/auth/pin-token</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">02</span><div class="frow"><span class="method post">POST</span><code>/pos/session/open</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">03</span><div class="frow"><span class="method post">POST</span><code>/pos/order/create</code></div></div><span class="farrow">&#8635;</span>
        <div class="fnode"><span class="fn">04</span><div class="frow"><span class="method post">POST</span><code>/pos/session/close</code></div></div><span class="farrow">&rarr;</span>
        <span class="fcap">Z-report</span>
      </div>
      <div class="steps">
        <article class="step">
          <div class="bar"><span class="sn">01</span><span class="method post">POST</span><span class="path">/api/v1/auth/pin-token</span><span class="desc">PIN &rarr; token, auto-opens the session</span></div>
          <div class="body pair">
            <div><div class="io-label"><span class="pip req"></span>Request</div>
<pre class="code"><span class="b">{</span> <span class="k">"pin"</span>:<span class="s">"392582"</span>,
  <span class="k">"device_uid"</span>:<span class="s">"till-02"</span> <span class="b">}</span></pre></div>
            <div><div class="io-label"><span class="pip res"></span>Response <span class="status ok">200</span></div>
<pre class="code"><span class="b">{</span> <span class="k">"data"</span>:<span class="b">{</span> <span class="k">"access_token"</span>:<span class="s">"eyJ..."</span>,
   <span class="k">"expires_in"</span>:<span class="n">3600</span>,
   <span class="k">"default_config_id"</span>:<span class="n">2</span> <span class="b">}}</span></pre></div>
          </div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">02</span><span class="method post">POST</span><span class="path">/api/v1/pos/session/open</span><span class="desc">start the till</span></div>
          <div class="body"><div class="note info"><span class="ic">i</span><div>The token already resolves cashier + config, so the app sends <span class="path">{ config_id, opening_balance }</span> and gets back the <span class="path">session_id</span> &mdash; reused for every order in the shift.</div></div></div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">03</span><span class="method post">POST</span><span class="path">/api/v1/pos/order/create</span><span class="desc">ring a sale</span></div>
          <div class="body pair">
            <div><div class="io-label"><span class="pip req"></span>Request</div>
<pre class="code"><span class="b">{</span> <span class="k">"session_id"</span>:<span class="n">88</span>,
  <span class="k">"order_lines"</span>:<span class="b">[</span><span class="b">{</span> <span class="k">"product_id"</span>:<span class="n">533</span>, <span class="k">"qty"</span>:<span class="n">2</span> <span class="b">}]</span>,
  <span class="k">"payments"</span>:<span class="b">[</span><span class="b">{</span> <span class="k">"method_id"</span>:<span class="n">5</span>, <span class="k">"amount"</span>:<span class="n">5.22</span> <span class="b">}]</span> <span class="b">}</span></pre></div>
            <div><div class="io-label"><span class="pip res"></span>Response <span class="status ok">200</span></div>
<pre class="code"><span class="b">{</span> <span class="k">"data"</span>:<span class="b">{</span> <span class="k">"order_id"</span>:<span class="n">1041</span>,
   <span class="k">"name"</span>:<span class="s">"Order 00012"</span>,
   <span class="k">"amount_total"</span>:<span class="n">5.22</span> <span class="b">}}</span></pre></div>
          </div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">04</span><span class="method post">POST</span><span class="path">/api/v1/pos/session/close</span><span class="desc">cash up &amp; Z-report</span></div>
          <div class="body"><div class="note info"><span class="ic">i</span><div>Draft orders are auto-cancelled, the till is reconciled, and a cash summary is returned. If a mutation fails mid-close the whole call rolls back &mdash; a retry can't double-post.</div></div></div>
        </article>
      </div>
    </section>

    <section class="journey" id="dash">
      <div class="j-head"><div class="j-num t">03</div><div>
        <h2>Owner Dashboard <span class="server-tag t">Tenant &middot; Store</span></h2>
        <p>The dashboard app reuses the POS login, discovers which boards it may show, then pulls widget data per board. Two calls to a full screen.</p>
      </div></div>
      <div class="flow" role="list" aria-label="Call sequence">
        <span class="fcap">App</span><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">01</span><div class="frow"><span class="method post">POST</span><code>/dashboard/list</code></div></div><span class="farrow">&rarr;</span>
        <div class="fnode"><span class="fn">02</span><div class="frow"><span class="method post">POST</span><code>/dashboard/data</code></div></div><span class="farrow">&rarr;</span>
        <span class="fcap">Widgets</span>
      </div>
      <div class="steps">
        <article class="step">
          <div class="bar"><span class="sn">01</span><span class="method post">POST</span><span class="path">/api/v1/dashboard/list</span><span class="desc">which boards this user can open</span></div>
          <div class="body"><div><div class="io-label"><span class="pip res"></span>Response <span class="status ok">200</span> &middot; verified live</div>
<pre class="code"><span class="b">{</span> <span class="k">"data"</span>:<span class="b">{</span> <span class="k">"dashboards"</span>:<span class="b">[</span>
   <span class="b">{</span> <span class="k">"code"</span>:<span class="s">"pos_main"</span>, <span class="k">"name"</span>:<span class="s">"POS Performance"</span> <span class="b">}</span>,
   <span class="b">{</span> <span class="k">"code"</span>:<span class="s">"sales_main"</span>, <span class="k">"name"</span>:<span class="s">"Sales Overview"</span> <span class="b">}</span>
<span class="b">]</span> <span class="b">}}</span></pre></div></div>
        </article>
        <article class="step">
          <div class="bar"><span class="sn">02</span><span class="method post">POST</span><span class="path">/api/v1/dashboard/data</span><span class="desc">widgets for one board</span></div>
          <div class="body pair">
            <div><div class="io-label"><span class="pip req"></span>Request</div>
<pre class="code"><span class="b">{</span> <span class="k">"dashboard_code"</span>:<span class="s">"pos_main"</span>,
  <span class="k">"filters"</span>:<span class="b">{</span> <span class="k">"date_from"</span>:<span class="s">"2026-07-01"</span>,
    <span class="k">"date_to"</span>:<span class="s">"2026-07-18"</span> <span class="b">}</span> <span class="b">}</span></pre></div>
            <div><div class="io-label"><span class="pip res"></span>Response &middot; widgets[]</div>
<pre class="code"><span class="b">{</span> <span class="k">"data"</span>:<span class="b">{</span> <span class="k">"widgets"</span>:<span class="b">[</span>
   <span class="b">{</span> <span class="k">"type"</span>:<span class="s">"kpi"</span>, <span class="k">"name"</span>:<span class="s">"POS Sales"</span>,
     <span class="k">"value"</span>:<span class="n">1234.5</span>, <span class="k">"format"</span>:<span class="s">"currency"</span> <span class="b">}</span>
<span class="b">]</span> <span class="b">}}</span></pre></div>
          </div>
        </article>
      </div>
    </section>

    <section class="journey" id="tokens">
      <div class="j-head"><div class="j-num c" style="background:var(--ink-soft)">&middot;</div><div>
        <h2>Tokens &amp; scope &mdash; which key opens which door</h2>
        <p>One JWT secret signs everything, but a token minted for one surface is rejected by the other. The scope claim is the boundary.</p>
      </div></div>
      <div class="ref"><table>
        <thead><tr><th>Get a token</th><th>Server</th><th>Scope claim</th><th>Opens</th><th>Rejected by</th></tr></thead>
        <tbody>
          <tr>
            <td class="mono">POST /api/v1/auth/login<br>POST /api/v1/auth/pin-token</td>
            <td><span class="server-tag t">Tenant</span></td>
            <td class="mono">device_id<br>branch_id</td>
            <td class="mono">/api/v1/pos/*<br>/api/v1/dashboard/*<br>/api/v1/ai &middot; /chat</td>
            <td class="mono">/api/v1/saas/* <span class="no">&times;</span></td>
          </tr>
          <tr>
            <td class="mono">POST /api/v1/saas/auth/login<br>.../login_by_client_number</td>
            <td><span class="server-tag c">Central</span></td>
            <td class="mono">partner_id<br>scope: saas_billing</td>
            <td class="mono">/api/v1/saas/me/*<br>(profile, tenants, billing)</td>
            <td class="mono">/api/v1/pos/* <span class="no">&times;</span></td>
          </tr>
        </tbody>
      </table></div>
      <div class="note info" style="margin-top:16px"><span class="ic">i</span><div><b>Both surfaces share the exact same schema per tenant</b> &mdash; only the data differs. So one reference instance documents the POS API for every tenant; you never need per-instance docs. Send the token on every call as <span class="path">Authorization: Bearer &lt;access_token&gt;</span>; access tokens last 1h, refresh tokens 30d (single-use on the portal). A <span class="path">401</span> with <span class="path">code: TOKEN_EXPIRED</span> is your cue to refresh, not to log out.</div></div>
    </section>
  </main>
</div></div>
<footer><div class="wrap">
  <span>Ghaima API &middot; lifecycle field guide &mdash; payloads captured from a live trace.</span>
  <span>Reference: <a href="/api/v1/docs">Swagger</a> &middot; <a href="/api/v1/guide">Guide</a></span>
</div></footer>
<script>
(function(){var r=document.documentElement,k="ghaima-docs-theme",s=null;
try{s=localStorage.getItem(k);}catch(e){}
if(s){r.setAttribute("data-theme",s);}
var b=document.getElementById("tt");
if(b){b.addEventListener("click",function(){
  var cur=r.getAttribute("data-theme")||(window.matchMedia&&window.matchMedia("(prefers-color-scheme:dark)").matches?"dark":"light");
  var nx=cur==="dark"?"light":"dark";r.setAttribute("data-theme",nx);
  try{localStorage.setItem(k,nx);}catch(e){}
});}
})();
</script>
</body>
</html>"""
