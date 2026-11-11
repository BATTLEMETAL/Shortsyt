# -*- coding: utf-8 -*-
import os
import shutil
import re

HEAD_ICONS = """  <!-- Favicon & App Icons (100% consistent with TikTok Basic Info 1024x1024 requirement) -->
  <link rel="icon" type="image/png" sizes="1024x1024" href="icon.png?v=20261027_2">
  <link rel="icon" type="image/png" sizes="64x64" href="favicon.png?v=20261027_2">
  <link rel="icon" type="image/x-icon" href="favicon.ico?v=20261027_2">
  <link rel="shortcut icon" href="favicon.ico?v=20261027_2">
  <link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261027_2">

  <!-- Canonical & Open Graph -->
  <link rel="canonical" href="https://shortsyt.salon-prettywoman.pl/">
  <meta property="og:title" content="Shortsyt Studio — Autonomous Gaming Short-Form Platform">
  <meta property="og:description" content="AI highlight detection, dynamic 9:16 vertical camera tracking, automated thumbnails, and multi-platform publishing for TikTok, YouTube Shorts, and Instagram Reels.">
  <meta property="og:image" content="https://shortsyt.salon-prettywoman.pl/icon.png?v=20261027_2">
  <meta property="og:image:width" content="1024">
  <meta property="og:image:height" content="1024">
  <meta property="og:url" content="https://shortsyt.salon-prettywoman.pl/">
  <meta property="og:type" content="website">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Shortsyt Studio — Autonomous Gaming Short-Form Platform">
  <meta name="twitter:description" content="AI highlight detection, dynamic 9:16 vertical camera tracking, automated thumbnails, and multi-platform publishing for TikTok, YouTube Shorts, and Instagram Reels.">
  <meta name="twitter:image" content="https://shortsyt.salon-prettywoman.pl/icon.png?v=20261027_2">"""

def patch_index_html():
    with open('docs/index.html', 'r', encoding='utf-8') as f:
        html = f.read()

    # Replace head icons and og block
    pat = re.compile(r'  <!-- Favicon & App Icons.*?(\n\s*<style>)', re.DOTALL)
    html = pat.sub(HEAD_ICONS + r'\1', html)

    with open('docs/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("index.html head patched.")

PRIVACY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Privacy Policy — Shortsyt Studio</title>
  <meta name="description" content="Privacy Policy for Shortsyt Studio - League of Legends Shorts Automation.">
  <meta name="theme-color" content="#0A0E1A">

  <link rel="icon" type="image/png" sizes="1024x1024" href="icon.png?v=20261027_2">
  <link rel="icon" type="image/png" sizes="64x64" href="favicon.png?v=20261027_2">
  <link rel="shortcut icon" href="favicon.ico?v=20261027_2">
  <link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261027_2">

  <style>
    :root {
      --bg: #0A0E1A;
      --card-bg: #121624;
      --border: #1E2438;
      --gold: #C89B3C;
      --gold-light: #E5C269;
      --text: #E4D6B5;
      --text-muted: #8B8FA8;
      --text-white: #FFFFFF;
      --cyan: #00F2FE;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.7;
      padding: 0 20px;
    }
    .container { max-width: 820px; margin: 0 auto; padding: 40px 0 80px; }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 36px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: var(--text-white);
      font-weight: 800;
      font-size: 1.2rem;
    }
    .brand img {
      width: 38px;
      height: 38px;
      border-radius: 8px;
      border: 1px solid var(--gold);
    }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .nav-links a {
      color: var(--gold);
      text-decoration: none;
      font-size: 0.85rem;
      font-weight: 600;
    }
    .nav-links a:hover { text-decoration: underline; }

    h1 { font-size: 2.2rem; color: var(--text-white); margin-bottom: 8px; font-weight: 900; }
    .date { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 24px; }
    .highlight {
      background: rgba(200, 155, 60, 0.1);
      border-left: 4px solid var(--gold);
      padding: 16px 20px;
      border-radius: 8px;
      margin-bottom: 32px;
      color: var(--text-white);
      font-size: 0.95rem;
    }

    h2 { font-size: 1.25rem; color: var(--gold-light); margin: 32px 0 12px; font-weight: 700; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
    p { margin-bottom: 14px; font-size: 0.95rem; color: var(--text-muted); }
    ul { margin: 12px 0 20px 24px; color: var(--text-muted); font-size: 0.95rem; }
    li { margin-bottom: 8px; }
    code { font-family: monospace; background: var(--card-bg); border: 1px solid var(--border); padding: 2px 6px; border-radius: 4px; color: var(--cyan); }
    a { color: var(--gold); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <a href="index.html" class="brand">
        <img src="icon.png?v=20261027_2" alt="Shortsyt Studio">
        <span>Shortsyt Studio</span>
      </a>
      <div class="nav-links">
        <a href="index.html">&larr; Homepage</a>
        <a href="terms.html">Terms of Service</a>
        <a href="index.html#reviewer-sandbox">Reviewer Access</a>
      </div>
    </header>

    <h1>Privacy Policy</h1>
    <div class="date">Effective Date: October 20, 2026 (Updated: October 27, 2026)</div>

    <div class="highlight">
      <strong>Core Principle:</strong> Shortsyt Studio is a 100% desktop application that processes and renders video strictly on your local machine. We do not operate external tracking servers and we never collect, store, or sell your personal data.
    </div>

    <h2>1. Overview</h2>
    <p>Shortsyt Studio is an autonomous desktop video creation tool designed for gaming content creators. This Privacy Policy details how data is accessed, handled, and protected when using the desktop application and its integrations.</p>

    <h2>2. Data We Do Not Collect</h2>
    <p>Shortsyt does <strong>not</strong> collect personal information. Specifically:</p>
    <ul>
      <li>No user account credentials or passwords are sent to external servers.</li>
      <li>No tracking cookies, pixels, or third-party behavioral analytics are embedded in the app.</li>
      <li>No personal data or video files are sold, rented, or distributed to any third party.</li>
    </ul>

    <h2>3. TikTok Content Posting API Integration</h2>
    <p>When you connect your TikTok account to Shortsyt Studio via OAuth 2.0 PKCE:</p>
    <ul>
      <li><strong>Local Token Storage:</strong> Access tokens and refresh tokens are stored exclusively on your local computer in your local project workspace. They are never transmitted to any third-party or developer-owned backend.</li>
      <li><strong>Requested Scopes:</strong> We request only <code>video.publish</code>, <code>video.upload</code> (to upload video chunks on your behalf), and <code>user.info.basic</code> (to verify your username/avatar in the local desktop UI).</li>
      <li><strong>Immediate Revocation:</strong> You can disconnect and revoke access at any time via TikTok mobile app &gt; Settings &amp; Privacy &gt; Security &gt; Apps and Sessions &gt; Manage app permissions.</li>
    </ul>

    <h2>4. Video Processing &amp; Media Files</h2>
    <p>All video analysis (OCR, kill-feed detection) and FFmpeg 9:16 rendering happen locally on your PC. Rendered video files are uploaded directly from your machine to TikTok / YouTube / Meta servers over encrypted HTTPS connections.</p>

    <h2>5. Compliance with Platform Guidelines</h2>
    <p>Shortsyt operates in full accordance with the <a href="https://www.tiktok.com/legal/page/global/terms-of-service/en" target="_blank">TikTok Terms of Service</a> and <a href="https://www.tiktok.com/legal/page/global/community-guidelines/en" target="_blank">TikTok Community Guidelines</a>.</p>

    <h2>6. Contact</h2>
    <p>If you have any questions about this Privacy Policy or data security, please contact:</p>
    <p><strong>Email:</strong> <a href="mailto:dwannellenga@gmail.com">dwannellenga@gmail.com</a><br>
    <strong>Developer:</strong> Michał Zalewski<br>
    <strong>Website:</strong> <a href="https://shortsyt.salon-prettywoman.pl/">https://shortsyt.salon-prettywoman.pl/</a></p>

    <p style="margin-top: 40px;"><a href="index.html">&larr; Return to Shortsyt Studio Homepage</a></p>
  </div>
</body>
</html>"""

TERMS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Terms of Service — Shortsyt Studio</title>
  <meta name="description" content="Terms of Service for Shortsyt Studio - League of Legends Shorts Automation.">
  <meta name="theme-color" content="#0A0E1A">

  <link rel="icon" type="image/png" sizes="1024x1024" href="icon.png?v=20261027_2">
  <link rel="icon" type="image/png" sizes="64x64" href="favicon.png?v=20261027_2">
  <link rel="shortcut icon" href="favicon.ico?v=20261027_2">
  <link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261027_2">

  <style>
    :root {
      --bg: #0A0E1A;
      --card-bg: #121624;
      --border: #1E2438;
      --gold: #C89B3C;
      --gold-light: #E5C269;
      --text: #E4D6B5;
      --text-muted: #8B8FA8;
      --text-white: #FFFFFF;
      --cyan: #00F2FE;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      line-height: 1.7;
      padding: 0 20px;
    }
    .container { max-width: 820px; margin: 0 auto; padding: 40px 0 80px; }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 36px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: var(--text-white);
      font-weight: 800;
      font-size: 1.2rem;
    }
    .brand img {
      width: 38px;
      height: 38px;
      border-radius: 8px;
      border: 1px solid var(--gold);
    }
    .nav-links {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .nav-links a {
      color: var(--gold);
      text-decoration: none;
      font-size: 0.85rem;
      font-weight: 600;
    }
    .nav-links a:hover { text-decoration: underline; }

    h1 { font-size: 2.2rem; color: var(--text-white); margin-bottom: 8px; font-weight: 900; }
    .date { color: var(--text-muted); font-size: 0.85rem; margin-bottom: 24px; }

    h2 { font-size: 1.25rem; color: var(--gold-light); margin: 32px 0 12px; font-weight: 700; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
    p { margin-bottom: 14px; font-size: 0.95rem; color: var(--text-muted); }
    ul { margin: 12px 0 20px 24px; color: var(--text-muted); font-size: 0.95rem; }
    li { margin-bottom: 8px; }
    a { color: var(--gold); }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <a href="index.html" class="brand">
        <img src="icon.png?v=20261027_2" alt="Shortsyt Studio">
        <span>Shortsyt Studio</span>
      </a>
      <div class="nav-links">
        <a href="index.html">&larr; Homepage</a>
        <a href="privacy.html">Privacy Policy</a>
        <a href="index.html#reviewer-sandbox">Reviewer Access</a>
      </div>
    </header>

    <h1>Terms of Service</h1>
    <div class="date">Effective Date: October 20, 2026 (Updated: October 27, 2026)</div>

    <h2>1. Description of Service</h2>
    <p>Shortsyt Studio is an autonomous desktop video automation tool that identifies highlight moments in gameplay video recordings, renders vertical 9:16 short-form video clips with visual effects, and publishes them to authorized social media platforms (TikTok, YouTube Shorts, Meta Reels) on behalf of the account owner.</p>

    <h2>2. User Obligations &amp; Compliance</h2>
    <p>By using Shortsyt Studio to upload and publish content to TikTok, you agree to comply strictly with:</p>
    <ul>
      <li><a href="https://www.tiktok.com/legal/page/global/terms-of-service/en" target="_blank">TikTok Terms of Service</a></li>
      <li><a href="https://www.tiktok.com/legal/page/global/community-guidelines/en" target="_blank">TikTok Community Guidelines</a></li>
      <li>Copyright laws and intellectual property rights concerning gaming footage and background audio.</li>
    </ul>

    <h2>3. Authentication &amp; API Usage</h2>
    <p>Shortsyt Studio connects to third-party services exclusively via standard OAuth 2.0 PKCE authentication authorized directly by the user. You retain full control over your connected accounts and may revoke access at any time through platform security settings.</p>

    <h2>4. Limitation of Liability</h2>
    <p>Shortsyt Studio is provided on an "as-is" and "as-available" basis without warranties of any kind. The developers are not liable for any content moderation decisions, account suspensions, or service disruptions imposed by third-party social media platforms.</p>

    <h2>5. Contact Information</h2>
    <p>For support, questions, or inquiries regarding these Terms of Service, contact:</p>
    <p><strong>Email:</strong> <a href="mailto:dwannellenga@gmail.com">dwannellenga@gmail.com</a><br>
    <strong>Developer:</strong> Michał Zalewski<br>
    <strong>Website:</strong> <a href="https://shortsyt.salon-prettywoman.pl/">https://shortsyt.salon-prettywoman.pl/</a></p>

    <p style="margin-top: 40px;"><a href="index.html">&larr; Return to Shortsyt Studio Homepage</a></p>
  </div>
</body>
</html>"""

CALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TikTok OAuth Authorization &amp; Reviewer Sandbox — Shortsyt Studio</title>
  <meta name="description" content="TikTok OAuth 2.0 Callback and Developer Reviewer Sandbox for Shortsyt Studio.">
  <link rel="icon" type="image/png" sizes="1024x1024" href="icon.png?v=20261027_2">
  <link rel="icon" type="image/png" sizes="64x64" href="favicon.png?v=20261027_2">
  <link rel="shortcut icon" href="favicon.ico?v=20261027_2">
  <link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png?v=20261027_2">
  <style>
    :root {
      --bg: #0A0E1A;
      --card-bg: #121624;
      --border: #1E2438;
      --gold: #C89B3C;
      --gold-light: #E5C269;
      --text: #E4D6B5;
      --text-muted: #8B8FA8;
      --text-white: #FFFFFF;
      --cyan: #00F2FE;
      --pink: #FE2C55;
      --green: #22C55E;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
    }
    .card {
      background: var(--card-bg);
      padding: 36px;
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.6);
      max-width: 600px;
      width: 100%;
      border: 1px solid var(--border);
      text-align: center;
    }
    .brand-bar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      margin-bottom: 20px;
    }
    .brand-bar img {
      width: 44px;
      height: 44px;
      border-radius: 10px;
      border: 1px solid var(--gold);
    }
    h1 { font-size: 1.6rem; margin-bottom: 8px; color: var(--text-white); }
    .subtitle { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 20px; }
    .status { margin-top: 20px; padding: 14px; border-radius: 8px; font-weight: 600; font-size: 0.95rem; }
    .success { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid #22c55e; }
    .info { background: rgba(0, 242, 254, 0.1); color: var(--cyan); border: 1px solid rgba(0, 242, 254, 0.3); }
    .sandbox-box {
      margin-top: 24px;
      padding: 16px;
      background: #080B14;
      border: 1px solid var(--border);
      border-radius: 10px;
      text-align: left;
      font-size: 0.85rem;
      line-height: 1.8;
    }
    .code-box {
      margin-top: 16px;
      padding: 12px;
      background: #080B14;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--cyan);
      font-family: monospace;
      font-size: 0.9rem;
      word-break: break-all;
    }
    .btn {
      display: inline-block;
      margin-top: 24px;
      padding: 10px 20px;
      background: linear-gradient(135deg, var(--gold) 0%, var(--gold-light) 100%);
      color: #0A0E1A;
      font-weight: 700;
      text-decoration: none;
      border-radius: 8px;
      font-size: 0.9rem;
    }
    .links {
      margin-top: 20px;
      display: flex;
      justify-content: center;
      gap: 16px;
      font-size: 0.85rem;
    }
    .links a { color: var(--gold); text-decoration: none; }
    .links a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="card">
    <div class="brand-bar">
      <img src="icon.png?v=20261027_2" alt="Shortsyt Studio">
      <span style="font-weight: 800; font-size: 1.3rem; color: #FFF;">Shortsyt Studio</span>
    </div>

    <h1>TikTok OAuth 2.0 PKCE Callback</h1>
    <div class="subtitle">Secure authentication endpoint for TikTok Content Posting API v2.</div>

    <div id="status" class="status info">Listening for authorization code...</div>
    <div id="codeDisplay" class="code-box" style="display: none;"></div>

    <div class="sandbox-box">
      <div style="font-weight: 700; color: var(--gold); margin-bottom: 6px;">TikTok Reviewer Sandbox Specifications:</div>
      <div><strong>App ID:</strong> 7698664436617365511</div>
      <div><strong>Client Key:</strong> awszg03b9v3j8171</div>
      <div><strong>Flow:</strong> Authorization Code with PKCE (RFC 7636)</div>
      <div><strong>Scopes:</strong> <code>user.info.basic</code>, <code>video.upload</code>, <code>video.publish</code></div>
      <div><strong>Test Account:</strong> tester@shortsyt.salon-prettywoman.pl</div>
    </div>

    <a href="index.html" class="btn">&larr; Return to Shortsyt Homepage</a>

    <div class="links">
      <a href="privacy.html">Privacy Policy</a>
      <a href="terms.html">Terms of Service</a>
      <a href="index.html#reviewer-sandbox">Reviewer Credentials</a>
    </div>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    const error = params.get('error');
    const errorDesc = params.get('error_description');

    const status = document.getElementById('status');
    const codeDisplay = document.getElementById('codeDisplay');

    if (error) {
      status.textContent = '❌ Authorization failed: ' + (errorDesc || error);
      status.style.background = 'rgba(239, 68, 68, 0.15)';
      status.style.color = '#f87171';
      status.style.border = '1px solid #ef4444';
    } else if (code) {
      status.className = 'status success';
      status.textContent = '✅ Authorization code received successfully!';
      codeDisplay.textContent = 'Code: ' + code;
      codeDisplay.style.display = 'block';

      // Relay to local desktop daemon if running
      fetch('http://localhost:8989/callback' + window.location.search, { mode: 'no-cors' })
        .then(() => {})
        .catch(() => {});
    } else {
      status.textContent = 'ℹ️ Standby: Ready to receive TikTok OAuth 2.0 PKCE redirects.';
    }
  </script>
</body>
</html>"""

def build_all():
    patch_index_html()

    # Write root legal files
    with open('docs/privacy.html', 'w', encoding='utf-8') as f:
        f.write(PRIVACY_HTML)
    with open('docs/terms.html', 'w', encoding='utf-8') as f:
        f.write(TERMS_HTML)
    with open('docs/callback.html', 'w', encoding='utf-8') as f:
        f.write(CALLBACK_HTML)

    # Subfolder copies for folder-based routing compatibility
    os.makedirs('docs/privacy', exist_ok=True)
    os.makedirs('docs/terms', exist_ok=True)
    os.makedirs('docs/callback', exist_ok=True)

    with open('docs/privacy/index.html', 'w', encoding='utf-8') as f:
        f.write(PRIVACY_HTML.replace('icon.png', '/icon.png').replace('favicon', '/favicon').replace('apple-touch-icon', '/apple-touch-icon'))
    with open('docs/terms/index.html', 'w', encoding='utf-8') as f:
        f.write(TERMS_HTML.replace('icon.png', '/icon.png').replace('favicon', '/favicon').replace('apple-touch-icon', '/apple-touch-icon'))
    with open('docs/callback/index.html', 'w', encoding='utf-8') as f:
        f.write(CALLBACK_HTML.replace('icon.png', '/icon.png').replace('favicon', '/favicon').replace('apple-touch-icon', '/apple-touch-icon'))

    # Mirror to Desktop folder: C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt
    dest_dir = r'C:\Users\mz100\OneDrive\Pulpit\strona kopia\strona yt'
    if os.path.exists(dest_dir):
        for fname in ['index.html', 'privacy.html', 'terms.html', 'callback.html', 'icon.png', 'icon.jpg', 'favicon.ico', 'favicon.png', 'apple-touch-icon.png', 'app_icon_1024.png', 'live_stats.json']:
            src = os.path.join('docs', fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dest_dir, fname))
        
        # Mirror screenshots
        src_screenshots = os.path.join('docs', 'screenshots')
        dest_screenshots = os.path.join(dest_dir, 'screenshots')
        os.makedirs(dest_screenshots, exist_ok=True)
        for s in os.listdir(src_screenshots):
            shutil.copy2(os.path.join(src_screenshots, s), os.path.join(dest_screenshots, s))

    print("All site assets built and mirrored to desktop folder successfully!")

if __name__ == '__main__':
    build_all()
