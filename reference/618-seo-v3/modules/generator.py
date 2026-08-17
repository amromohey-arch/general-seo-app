import os
import json
import random
import string
from datetime import datetime
from modules.gemini_client import gemini

WEB3FORMS_KEY = os.environ.get('WEB3FORMS_ACCESS_KEY', 'YOUR_WEB3FORMS_KEY')

# ─── Tenant config ──────────────────────────────────────────────────────────
# BRAND_CONTEXT, FULL_CSS, and STYLE_REFERENCE below are computed from this
# config instead of hardcoded per-business values. See config/618-media.json
# for 618's data and memory/hardcoded-to-extract.md in the repo root for why.
_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CONFIG_PATH = os.path.normpath(os.path.join(_MODULES_DIR, '..', 'config', '618-media.json'))

_config_path_env = os.environ.get('CONFIG_PATH', '').strip()
if _config_path_env:
    # Relative overrides resolve against generator.py's own directory, the
    # same basis the default uses -- not the process's working directory,
    # which varies by how/where the app is launched (Cloud Run, local dev,
    # etc). Every future tenant's deployment will set this env var, so it's
    # about to become the primary path, not just the fallback.
    CONFIG_PATH = (
        _config_path_env if os.path.isabs(_config_path_env)
        else os.path.normpath(os.path.join(_MODULES_DIR, _config_path_env))
    )
else:
    CONFIG_PATH = _DEFAULT_CONFIG_PATH

# Every dotted path here is actually read via bracket access somewhere in
# _build_brand_context / _build_full_css -- verified field-by-field by
# removing each one from a real config and confirming it currently produces
# an uncaught KeyError, not a clean error. Deliberately NOT required because
# nothing reads them: brand.contact (incl. lead_form), content_rules.
# word_count_target, content_rules.style_reference_path,
# style.colors.background, tenant.id, tenant.preset.
_REQUIRED_CONFIG_PATHS = [
    'tenant.business_name',
    'brand.about',
    'brand.services',
    'brand.landmines',
    'brand.location.mention_rule',
    'content_rules.banned_words',
    'content_rules.article_perspective',
    'content_rules.first_person_allowed',
    'content_rules.no_fake_testimonials',
    'content_rules.keyword_stuffing_forbidden',
    'content_rules.primary_keyword_max_uses',
    'content_rules.faq_answers_must_be_written',
    'content_rules.writing_rules',
    'style.google_fonts_url',
    'style.fonts.body',
    'style.fonts.heading',
    'style.colors.accent',
    'style.colors.accent_hover',
    'style.colors.text',
    'style.colors.text_muted',
    'style.colors.border',
    'style.colors.accent_tint_bg',
    'style.colors.surface_alt',
]


def _load_tenant_config(path: str) -> dict:
    """Loads and validates the tenant config. The app must not start with a
    broken or missing config, so this still fails loudly -- but with a
    message naming the exact problem instead of a raw traceback."""
    if not os.path.exists(path):
        raise RuntimeError(
            f"Tenant config not found at '{path}'. Set the CONFIG_PATH env var "
            f"to a valid config file, or check that the default config exists."
        )
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Tenant config at '{path}' is not valid JSON: {e}") from e

    for dotted_path in _REQUIRED_CONFIG_PATHS:
        node = cfg
        for part in dotted_path.split('.'):
            if not isinstance(node, dict) or part not in node:
                raise RuntimeError(f"Tenant config at '{path}' is missing '{dotted_path}'.")
            node = node[part]

    for i, rule in enumerate(cfg['content_rules']['writing_rules']):
        for key in ('title', 'body'):
            if key not in rule:
                raise RuntimeError(
                    f"Tenant config at '{path}' is missing '{key}' on content_rules.writing_rules[{i}]."
                )

    return cfg


TENANT_CONFIG = _load_tenant_config(CONFIG_PATH)


def _load_style_reference(cfg: dict, config_path: str) -> str:
    """Optional style-matching reference article, sourced from config's
    content_rules.style_reference_path -- resolved relative to the config
    file's own directory (not generator.py's), so a tenant's config and its
    style reference travel together. Missing/unset is fine: this feature is
    opt-in, see generate_article_html's use of STYLE_REFERENCE."""
    rel_path = cfg.get('content_rules', {}).get('style_reference_path')
    if not rel_path:
        return ''
    config_dir = os.path.dirname(os.path.abspath(config_path))
    style_path = os.path.normpath(os.path.join(config_dir, rel_path))
    if not os.path.exists(style_path):
        return ''
    with open(style_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


STYLE_REFERENCE = _load_style_reference(TENANT_CONFIG, CONFIG_PATH)


def _build_brand_context(cfg: dict) -> str:
    """Rebuilds the brand/rules prompt block from tenant config. Bullet order
    and writing-rule formatting match the original hardcoded BRAND_CONTEXT
    layout exactly (verified byte-for-byte before this refactor landed)."""
    brand = cfg['brand']
    rules_cfg = cfg['content_rules']
    year = datetime.now().year

    bullets = list(brand['landmines'])
    bullets.append('NEVER use: ' + ', '.join(rules_cfg['banned_words']))
    if not rules_cfg['first_person_allowed']:
        bullets.append('NEVER use first person I — write as expert industry advice')
    bullets.append('Services: ' + ', '.join(brand['services']))
    bullets.append('LOCATION RULE: ' + brand['location']['mention_rule'])
    if rules_cfg['no_fake_testimonials']:
        bullets.append('No made-up client quotes or fake testimonials')
    bullets.append(f'THE CURRENT YEAR IS {year}. Never write {year - 2} or {year - 1} anywhere')
    if rules_cfg['keyword_stuffing_forbidden']:
        bullets.append(
            f"KEYWORD STUFFING IS FORBIDDEN. Primary keyword max {rules_cfg['primary_keyword_max_uses']} "
            f"uses total. Use semantic variants everywhere else"
        )
    if rules_cfg['faq_answers_must_be_written']:
        bullets.append('FAQ answers MUST be fully written — never a question without an answer')
    bullets.append('ARTICLE PERSPECTIVE: ' + rules_cfg['article_perspective'])

    bullets_text = '\n'.join(f'- {b}' for b in bullets)

    writing_rules = rules_cfg['writing_rules']
    rules_text = '\n\n'.join(
        f"RULE {i + 1} — {r['title']}:\n{r['body']}" for i, r in enumerate(writing_rules)
    )

    return (
        f"ABOUT {cfg['tenant']['business_name'].upper()}:\n"
        f"{brand['about']}\n\n"
        f"STRICT BRAND RULES — NEVER BREAK THESE:\n"
        f"{bullets_text}\n\n"
        f"{len(writing_rules)} WRITING RULES — APPLY TO EVERY ARTICLE:\n\n"
        f"{rules_text}"
    ).strip()


# Shared CSS structure (layout, class names, the FAQ accordion, form styling)
# stays fixed here — it isn't business-specific. Only the @@TOKEN@@ spots are
# brand identity (colors/fonts) and get substituted from tenant config.
# Deliberately NOT tokenized: #E8E5E0 (image placeholder gray), #fff/#ffffff
# (used for contrast in several unrelated structural spots, not one
# consistent "background" concept), rgba(...) tints derived from accent/white,
# error-state colors (#f5c6bc/#fff0ee/#c0392b), and the box-shadow. Those are
# UI-state/structural colors, not brand identity, so they stay fixed literals.
_CSS_TEMPLATE = """@import url('@@GOOGLE_FONTS_URL@@');
.aw *,.aw *::before,.aw *::after{box-sizing:border-box}
.aw{font-family:@@FONT_BODY@@;color:@@TEXT@@;-webkit-font-smoothing:antialiased;font-size:16px;line-height:1.75;width:100%;max-width:740px;margin:0 auto;padding:2.5rem 1.25rem 4rem}
.aw .aey{font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:@@ACCENT@@;display:block;margin-bottom:.65rem}
.aw .at{font-family:@@FONT_HEADING@@;font-size:clamp(1.75rem,5vw,2.6rem);line-height:1.15;color:@@TEXT@@;margin-bottom:.65rem}
.aw .am{font-size:13px;color:@@TEXT_MUTED@@;margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:2px solid @@BORDER@@}
.aw .am span{margin-right:1rem}
.aw .aimg{width:100%;aspect-ratio:16/9;background:#E8E5E0;border-radius:10px;margin:1.75rem 0;display:flex;align-items:center;justify-content:center;overflow:hidden}
.aw .aimg img{width:100%;height:100%;object-fit:cover;border-radius:10px}
.aw .ab h2{font-family:@@FONT_HEADING@@;font-size:clamp(1.2rem,3.5vw,1.65rem);color:@@TEXT@@;margin:2.25rem 0 .65rem;line-height:1.25}
.aw .ab h3{font-size:1.05rem;font-weight:700;color:@@TEXT@@;margin:1.5rem 0 .5rem}
.aw .ab p{margin-bottom:1.15rem;color:@@TEXT@@}
.aw .ab ul,.aw .ab ol{margin:.75rem 0 1.15rem 1.5rem}
.aw .ab li{margin-bottom:.5rem;color:@@TEXT@@}
.aw .ab strong{font-weight:700}
.aw .ab a{color:@@ACCENT@@ !important;text-decoration:none !important;border-bottom:1px solid rgba(@@ACCENT_RGB@@,.3);transition:border-color .15s}
.aw .ab a:hover{border-color:@@ACCENT@@ !important}
.aw .apq{border-left:3px solid @@ACCENT@@;padding:.9rem 1.25rem;margin:1.75rem 0;background:@@ACCENT_TINT_BG@@;border-radius:0 8px 8px 0;font-family:@@FONT_HEADING@@;font-size:1.05rem;color:@@TEXT@@;font-style:italic;line-height:1.6}
.aw .atip{background:@@TEXT@@;border-radius:10px;padding:1.25rem 1.5rem;margin:1.75rem 0}
.aw .atip-label{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:@@ACCENT@@;display:block;margin-bottom:.45rem}
.aw .atip p{color:rgba(255,255,255,.8);font-size:14px;line-height:1.7;margin:0}
.aw .atbw{overflow-x:auto;-webkit-overflow-scrolling:touch;border-radius:8px;margin:1.5rem 0;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.aw .atb{width:100%;border-collapse:collapse;font-size:14px;min-width:360px}
.aw .atb thead tr{background:@@TEXT@@;color:#fff}
.aw .atb thead th{padding:11px 13px;text-align:left;font-weight:600;letter-spacing:.02em}
.aw .atb tbody tr:nth-child(odd){background:#fff}
.aw .atb tbody tr:nth-child(even){background:@@SURFACE_ALT@@}
.aw .atb tbody tr:hover{background:#EEE8E0;transition:background .15s}
.aw .atb tbody td{padding:10px 13px;border-bottom:1px solid @@BORDER@@;color:@@TEXT@@;line-height:1.5;vertical-align:top}
.aw .atb tbody td:first-child{font-weight:600}
.aw .afaq{margin:2.25rem 0}
.aw .afaq-t{font-family:@@FONT_HEADING@@;font-size:1.45rem;color:@@TEXT@@;margin-bottom:.9rem}
.aw .afaq-item{border-bottom:1px solid @@BORDER@@}
.aw .afaq-btn{width:100%;background:none;border:none;padding:.9rem 0;display:flex;align-items:center;justify-content:space-between;gap:.9rem;cursor:pointer;text-align:left}
.aw .afaq-q{font-size:15px;font-weight:600;color:@@TEXT@@;line-height:1.4}
.aw .afaq-ic{flex-shrink:0;width:22px;height:22px;border-radius:50%;border:1.5px solid @@BORDER@@;position:relative;transition:background .16s,border-color .16s}
.aw .afaq-ic::before,.aw .afaq-ic::after{content:'';position:absolute;top:50%;left:50%;background:@@TEXT_MUTED@@;border-radius:2px;transition:opacity .2s,transform .2s}
.aw .afaq-ic::before{width:10px;height:1.5px;transform:translate(-50%,-50%)}
.aw .afaq-ic::after{width:1.5px;height:10px;transform:translate(-50%,-50%)}
.aw .afaq-item.open .afaq-ic{background:@@ACCENT@@;border-color:@@ACCENT@@}
.aw .afaq-item.open .afaq-ic::before,.aw .afaq-item.open .afaq-ic::after{background:#fff}
.aw .afaq-item.open .afaq-ic::after{transform:translate(-50%,-50%) rotate(90deg);opacity:0}
.aw .afaq-btn:hover .afaq-q{color:@@ACCENT@@}
.aw .afaq-btn:hover .afaq-ic{border-color:@@ACCENT@@}
.aw .afaq-panel{max-height:0;overflow:hidden;opacity:0;transition:max-height .35s cubic-bezier(.4,0,.2,1),opacity .3s,padding-bottom .3s}
.aw .afaq-item.open .afaq-panel{opacity:1;padding-bottom:1rem}
.aw .afaq-a{font-size:14px;color:@@TEXT_MUTED@@;line-height:1.75}
.aw .aabout{background:@@TEXT@@;border-radius:12px;padding:1.65rem;margin:2.5rem 0 2rem;position:relative;overflow:hidden}
.aw .aabout::before{content:'';position:absolute;top:-40px;right:-40px;width:160px;height:160px;background:radial-gradient(circle,rgba(@@ACCENT_RGB@@,.2) 0%,transparent 70%);pointer-events:none}
.aw .aabout-lbl{font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:@@ACCENT@@;display:block;margin-bottom:.5rem}
.aw .aabout p{font-size:13.5px;color:rgba(255,255,255,.7);line-height:1.65;margin-bottom:.8rem}
.aw .aabout-cta{display:inline-block;background:@@ACCENT@@ !important;color:#ffffff !important;font-weight:700;font-size:13.5px;padding:.65rem 1.35rem;border-radius:8px;text-decoration:none !important;transition:background .16s}
.aw .aabout-cta:hover{background:@@ACCENT_HOVER@@ !important}
.aw .accta{background:@@ACCENT_TINT_BG@@;border:1.5px solid rgba(@@ACCENT_RGB@@,.25);border-radius:12px;padding:1.35rem;margin:2rem 0;display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.aw .accta p{font-size:14px;color:@@TEXT@@;line-height:1.55;flex:1;min-width:180px}
.aw .accta p strong{color:@@ACCENT@@}
.aw .accta-btn{display:inline-block;background:@@ACCENT@@ !important;color:#ffffff !important;font-weight:700;font-size:13.5px;padding:.65rem 1.35rem;border-radius:8px;text-decoration:none !important;white-space:nowrap;transition:background .16s,transform .12s}
.aw .accta-btn:hover{background:@@ACCENT_HOVER@@ !important;transform:translateY(-1px)}
.aw .afw{background:#fff;border:2px solid @@BORDER@@;border-radius:12px;padding:1.65rem;margin:2rem 0}
.aw .afh{font-family:@@FONT_HEADING@@;font-size:1.3rem;color:@@TEXT@@;margin-bottom:.3rem}
.aw .afss{font-size:13px;color:@@TEXT_MUTED@@;margin-bottom:1.1rem;line-height:1.6}
.aw .afrow{display:grid;grid-template-columns:1fr 1fr;gap:.7rem;margin-bottom:.7rem}
@media(max-width:480px){.aw .afrow{grid-template-columns:1fr}}
.aw .afg{margin-bottom:.7rem}
.aw .aflbl{font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:@@TEXT_MUTED@@;display:block;margin-bottom:.3rem}
.aw .afin,.aw .afta{width:100%;padding:.65rem .85rem;border:2px solid @@BORDER@@;border-radius:8px;font-family:@@FONT_BODY@@;font-size:15px;color:@@TEXT@@;background:@@SURFACE_ALT@@;outline:none;transition:border-color .16s}
.aw .afin:focus,.aw .afta:focus{border-color:@@ACCENT@@;background:#fff}
.aw .afta{resize:vertical;min-height:80px}
.aw .afsub{width:100%;padding:.85rem;font-size:15px;background:@@ACCENT@@ !important;color:#ffffff !important;border:none;border-radius:8px;font-family:@@FONT_BODY@@;font-weight:700;cursor:pointer;transition:background .16s;display:flex;align-items:center;justify-content:center;gap:.5rem}
.aw .afsub:hover:not(:disabled){background:@@ACCENT_HOVER@@ !important}
.aw .afsub:disabled{opacity:.55;cursor:not-allowed}
.aw .afpriv{font-size:11px;color:@@TEXT_MUTED@@;text-align:center;margin-top:.6rem;line-height:1.5}
.aw .aferr{background:#fff0ee;border:1.5px solid #f5c6bc;border-radius:8px;padding:.75rem .9rem;font-size:13px;color:#c0392b;margin-bottom:.65rem;display:none;line-height:1.5}
.aw .aferr.on{display:block}
.aw .afspin{width:15px;height:15px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:awspin .7s linear infinite;display:none}
.aw .afspin.on{display:block}
@keyframes awspin{to{transform:rotate(360deg)}}
.aw .afconf{text-align:center;padding:1.25rem;display:none}
.aw .afconf.on{display:block}
.aw .afconf p{color:@@TEXT_MUTED@@;font-size:14px;line-height:1.65}
.aw .asrc{margin:2rem 0 1rem;padding-top:1.5rem;border-top:1px solid @@BORDER@@}
.aw .asrc-t{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:@@TEXT_MUTED@@;margin-bottom:.7rem;display:block}
.aw .asrc ol{margin-left:1.25rem}
.aw .asrc li{font-size:12px;color:@@TEXT_MUTED@@;margin-bottom:.3rem;line-height:1.5}
.aw .asrc a{color:@@ACCENT@@ !important;text-decoration:none !important}
.aw .asrc a:hover{text-decoration:underline !important}
@media(max-width:600px){.aw{padding:1.75rem .9rem 3rem}.aw .accta{flex-direction:column}.aw .accta-btn{width:100%;text-align:center;display:block}}"""


def _hex_to_rgb_str(hex_color: str) -> str:
    """'#E5421A' -> '229,66,26', for building rgba(...) values from a hex token."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'{r},{g},{b}'


def _build_full_css(cfg: dict) -> str:
    """Substitutes brand color/font tokens into the shared CSS structure."""
    style = cfg['style']
    colors = style['colors']
    fonts = style['fonts']
    css = _CSS_TEMPLATE
    css = css.replace('@@GOOGLE_FONTS_URL@@', style['google_fonts_url'])
    css = css.replace('@@FONT_BODY@@', fonts['body'])
    css = css.replace('@@FONT_HEADING@@', fonts['heading'])
    css = css.replace('@@ACCENT_HOVER@@', colors['accent_hover'])
    css = css.replace('@@ACCENT_TINT_BG@@', colors['accent_tint_bg'])
    css = css.replace('@@ACCENT_RGB@@', _hex_to_rgb_str(colors['accent']))
    css = css.replace('@@ACCENT@@', colors['accent'])
    css = css.replace('@@TEXT_MUTED@@', colors['text_muted'])
    css = css.replace('@@TEXT@@', colors['text'])
    css = css.replace('@@BORDER@@', colors['border'])
    css = css.replace('@@SURFACE_ALT@@', colors['surface_alt'])
    return css


BRAND_CONTEXT = _build_brand_context(TENANT_CONFIG)
FULL_CSS = _build_full_css(TENANT_CONFIG)


def assemble_spotlight_html(body, sources, seo_title, year=None):
    """Same brand shell as _assemble_html (CSS, byline, About block, contact
    form) but skips the pricing table, FAQ, and Calculator CTA — none of
    those fit commentary content. Adds a real sources block instead, built
    from the actual search results the article was grounded in, not from
    the model attributing a citation to memory."""
    import datetime as _dt
    year = year or _dt.datetime.now().year
    uid = _uid()
    article_title = seo_title.replace(' | 618 Media', '').strip()

    about_html = (
        '<div class="aabout"><span class="aabout-lbl">About 618 Media</span>'
        '<p>618 Media is a video production company based in NSW, working with businesses, artists, and organisations across Sydney and NSW on music videos, brand stories, corporate video, event coverage, real estate, social media content, and more.</p>'
        '<p>Every project starts with a conversation about what you want to achieve. We handle everything from concept through to final delivery.</p>'
        '<a href="https://www.618media.com.au/contact-us" class="aabout-cta" style="color:#ffffff !important">Get in Touch</a></div>'
    )

    sources_html = ''
    if sources:
        links = ''.join(
            f'<li><a href="{s.get("uri", "")}" target="_blank" rel="noopener">{s.get("title") or s.get("domain") or s.get("uri", "")}</a></li>'
            for s in sources if s.get('uri')
        )
        if links:
            sources_html = f'<div class="asrc"><span class="asrc-lbl">Sources</span><ul>{links}</ul></div>'

    form_html = (
        f'<div class="afw"><h3 class="afh">Start Your Project or Ask a Question</h3>'
        f'<p class="afss">Fill in your details and a member of the 618 Media team will get back to you personally.</p>'
        f'<div class="aferr" id="aferr{uid}">Something went wrong. Please try again or email us at <strong>info@618media.com.au</strong></div>'
        f'<div id="aform{uid}"><div class="afrow">'
        f'<div class="afg"><label class="aflbl">Name *</label><input class="afin" type="text" id="afn{uid}" placeholder="Your full name"></div>'
        f'<div class="afg"><label class="aflbl">Phone *</label><input class="afin" type="tel" id="afp{uid}" placeholder="04XX XXX XXX"></div>'
        f'</div><div class="afg"><label class="aflbl">Email *</label><input class="afin" type="email" id="afe{uid}" placeholder="you@example.com"></div>'
        f'<div class="afg"><label class="aflbl">Your question or project idea</label><textarea class="afta" id="afq{uid}" placeholder="Tell us what you are working on..."></textarea></div>'
        f'<button type="button" class="afsub" id="afsub{uid}" style="color:#ffffff !important">'
        f'<span id="afsubt{uid}">Send Message</span><span class="afspin" id="afspin{uid}"></span></button>'
        f'<p class="afpriv">A team member reviews every message personally. No automated replies.</p></div>'
        f'<div class="afconf" id="afconf{uid}"><span style="font-size:2rem;display:block;margin-bottom:.5rem">&#127916;</span>'
        f'<p><strong>Message received.</strong> The 618 Media team will get back to you personally, usually within a few hours on business days.</p></div></div>'
    )

    js = (
        f'<script>\n(function(){{\n'
        f'  var b=document.getElementById("afsub{uid}");\n'
        f'  if(!b)return;\n'
        f'  b.addEventListener("click",async function(){{\n'
        f'    var n=document.getElementById("afn{uid}").value.trim();\n'
        f'    var p=document.getElementById("afp{uid}").value.trim();\n'
        f'    var e=document.getElementById("afe{uid}").value.trim();\n'
        f'    var q=document.getElementById("afq{uid}").value.trim();\n'
        f'    var err=document.getElementById("aferr{uid}");\n'
        f'    var spin=document.getElementById("afspin{uid}");\n'
        f'    var txt=document.getElementById("afsubt{uid}");\n'
        f'    if(!n||!p||!e){{alert("Please fill in your name, phone number, and email.");return;}}\n'
        f'    b.disabled=true;txt.textContent="Sending...";spin.classList.add("on");err.classList.remove("on");\n'
        f'    try{{\n'
        f'      var r=await fetch("https://api.web3forms.com/submit",{{method:"POST",headers:{{"Content-Type":"application/json","Accept":"application/json"}},body:JSON.stringify({{"access_key":"{WEB3FORMS_KEY}","subject":"Enquiry: {article_title}","from_name":"618 Media Blog","name":n,"email":e,"phone":p,"message":"Name: "+n+"\\nPhone: "+p+"\\nEmail: "+e+"\\nArticle: {article_title}"+"\\nQuestion: "+q,"botcheck":""}})}});\n'
        f'      var d=await r.json();\n'
        f'      if(d.success){{document.getElementById("aform{uid}").style.display="none";document.getElementById("afconf{uid}").classList.add("on");}}\n'
        f'      else throw new Error(d.message||"failed");\n'
        f'    }}catch(ex){{err.classList.add("on");b.disabled=false;txt.textContent="Send Message";spin.classList.remove("on");}}\n'
        f'  }});\n'
        f'  var y=new Date().getFullYear().toString();\n'
        f'  document.querySelectorAll("#aw{uid} .auto-year").forEach(function(el){{el.textContent=y;}});\n'
        f'}})();\n</script>'
    )

    return (
        f'<style>\n{FULL_CSS}\n.aw .asrc{{margin:1.75rem 0;padding-top:1.25rem;border-top:1px solid #E0DDD8}}'
        f'.aw .asrc-lbl{{font-size:10px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#888;display:block;margin-bottom:.5rem}}'
        f'.aw .asrc ul{{margin:0;padding-left:1.1rem}}.aw .asrc a{{color:#555;font-size:13px}}\n</style>\n\n'
        f'<div class="aw" id="aw{uid}">\n'
        f'  <div class="am"><span>By 618 Media</span><span>Updated <span class="auto-year">{year}</span></span><span>Sydney &amp; NSW</span></div>\n'
        f'  <div class="ab">\n{body}\n  </div>\n'
        f'  {sources_html}\n'
        f'  {about_html}\n'
        f'  {form_html}\n'
        f'</div>\n{js}'
    )


def build_image_html(seo_title: str, image_url: str = None, image_data: str = None) -> str:
    if image_url:
        alt = seo_title.replace(' | 618 Media', '').strip()
        return f'  <div class="aimg"><img src="{image_url}" alt="{alt}"></div>\n'
    if image_data:
        alt = seo_title.replace(' | 618 Media', '').strip()
        return f'  <div class="aimg"><img src="{image_data}" alt="{alt}"></div>\n'
    return ''


def reassemble_article_html(body, table_data, faq_items, seo_title, image_url=None, image_data=None, year=None):
    """Rebuilds the final HTML from already-generated pieces — used when only
    the image is changing. No AI call needed: adding a picture is a structural
    edit, not a rewrite, so this is instant and free."""
    year = year or datetime.now().year
    uid = _uid()
    image_html = build_image_html(seo_title, image_url, image_data)
    fragment = _assemble_html(
        uid=uid, body=body, table_data=table_data, faq_items=faq_items or [],
        seo_title=seo_title, year=year, image_html=image_html,
    )
    return fragment


def _uid():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=3))


def generate_seo_title_description(cluster: dict, answers: dict = None) -> dict:
    import json as _json
    from modules.gemini_client import gemini as _gemini
    answers = answers or {}
    cluster_name = cluster.get('cluster_name', '')
    primary_kw = cluster.get('primary_keyword', '')
    search_intent = cluster.get('search_intent', '')
    answers_text = ', '.join(str(v) for v in answers.values() if v)
    prompt = (
        'You are an SEO expert for 618 Media, a video production company in Sydney and NSW, Australia.\n'
        'Generate an SEO title and meta description for a blog article.\n'
        'Cluster: ' + cluster_name + '\n'
        'Primary keyword: ' + primary_kw + '\n'
        'Search intent: ' + search_intent + '\n'
        'Context: ' + (answers_text if answers_text else 'None') + '\n'
        'Rules for SEO title: 50-60 chars, include primary keyword, end with | 618 Media.\n'
        'Rules for meta description: 130-160 chars. Must directly answer what the searcher wants to know. '
        'Include a specific fact, number, or price range if relevant. Include primary keyword. '
        'No hollow phrases like: stunning, captivating, seamless, look no further, explore, discover.\n'
        'Good example: Wedding videography in Sydney costs $3,000-$8,500 depending on hours and deliverables. '
        'This guide covers what drives price and how to choose the right team.\n'
        'Return ONLY a JSON object with keys seo_title and seo_description. No other text.'
    )
    text = _gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
    return _json.loads(text)


def generate_copilot_questions(cluster: dict) -> list:
    prompt = (
        f"{BRAND_CONTEXT}\n\n"
        "Generate exactly 3 copilot questions to help 618 Media write a better article.\n\n"
        "IMPORTANT: These questions are asked TO the article author at 618 Media, NOT to a customer.\n"
        "The goal is to understand what 618 Media knows, has experienced, or wants to say about this topic.\n"
        "Questions should uncover: relevant 618 Media experience, specific angle or tone they want, nuance about the audience.\n\n"
        "Examples of good questions:\n"
        "- What type of clients does 618 Media most often work with for this service?\n"
        "- What is the most common misconception clients have about this topic?\n"
        "- What tone should this article take?\n\n"
        f"Article topic: {cluster.get('cluster_name')}\n"
        f"Angle: {cluster.get('article_angle')}\n"
        f"Primary keyword: {cluster.get('primary_keyword')}\n"
        f"Search intent: {cluster.get('search_intent')}\n\n"
        "For each question choose the best format from: multiple_choice, checkboxes, dropdown, linear_scale, grid\n\n"
        "Return ONLY a JSON array. Each object must have:\n"
        "- id: snake_case identifier\n"
        "- question: question addressed to the article author\n"
        "- format: one of the formats above\n"
        "- options: array of 3-5 option strings\n"
        "- scale_min: string label for linear_scale min, null otherwise\n"
        "- scale_max: string label for linear_scale max, null otherwise\n"
        "- grid_rows: array of row labels for grid, null otherwise\n"
        "- grid_cols: array of column labels for grid, null otherwise\n\n"
        "No other text."
    )
    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Generator] Questions error: {e}")
        return []


def build_prompt_summary(cluster: dict, answers: dict, seo_title: str, seo_description: str, blueprint_sections: list = None) -> dict:
    year = datetime.now().year
    summary = {
        'topic': cluster.get('cluster_name', ''),
        'angle': cluster.get('article_angle', ''),
        'search_intent': cluster.get('search_intent', ''),
        'ai_search_angle': cluster.get('ai_search_angle', ''),
        'primary_keyword': cluster.get('primary_keyword', ''),
        'secondary_keywords': cluster.get('secondary_keywords', []),
        'paa_questions': cluster.get('paa_questions', []),
        'copilot_answers': answers,
        'seo_title': seo_title,
        'seo_description': seo_description,
        'year': year,
        'tone_notes': 'Direct, practical, expert advice. No keyword stuffing. Written for potential 618 Media clients.',
        'style_reference': 'Conference Video Coverage guide (Article 07) — used as tone and structure benchmark',
        'sections_planned': blueprint_sections or [],
        'word_count_target': '900-1200 words',
    }
    return summary


def _assemble_html(uid, body, table_data, faq_items, seo_title, year, image_html=''):
    article_title = seo_title.replace(' | 618 Media', '').strip()

    table_html = ''
    if table_data and table_data.get('headers'):
        headers = ''.join(f'<th>{h}</th>' for h in table_data['headers'])
        rows = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in table_data.get('rows', []))
        footnote = table_data.get('footnote', 'All price ranges are estimates only. Contact 618 Media or use the Video Project Calculator for a tailored quote.')
        table_html = (
            f'<div class="atbw"><table class="atb"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p style="font-size:12px;color:#888;margin-top:.5rem;font-style:italic">{footnote}</p>'
        )

    faq_items_html = ''
    for item in faq_items:
        faq_items_html += (
            f'<div class="afaq-item"><button class="afaq-btn" aria-expanded="false">'
            f'<span class="afaq-q">{item.get("q","")}</span>'
            f'<span class="afaq-ic" aria-hidden="true"></span></button>'
            f'<div class="afaq-panel"><p class="afaq-a">{item.get("a","")}</p></div></div>'
        )
    faq_html = f'<div class="afaq"><h2 class="afaq-t">Frequently Asked Questions</h2>{faq_items_html}</div>'

    about_html = (
        '<div class="aabout"><span class="aabout-lbl">About 618 Media</span>'
        '<p>618 Media is a video production company based in NSW, working with businesses, artists, and organisations across Sydney and NSW on music videos, brand stories, corporate video, event coverage, real estate, social media content, and more.</p>'
        '<p>Every project starts with a conversation about what you want to achieve. We handle everything from concept through to final delivery.</p>'
        '<a href="https://www.618media.com.au/contact-us" class="aabout-cta" style="color:#ffffff !important">Get in Touch</a></div>'
    )

    cta_html = (
        '<div class="accta"><p><strong>Not sure what video you need?</strong> Use our free Video Project Calculator to get a tailored recommendation and rough estimate in under 2 minutes.</p>'
        '<a href="https://www.618media.com.au/my-video-calculator" class="accta-btn" style="color:#ffffff !important">Use the Calculator</a></div>'
    )

    form_html = (
        f'<div class="afw"><h3 class="afh">Start Your Project or Ask a Question</h3>'
        f'<p class="afss">Fill in your details and a member of the 618 Media team will get back to you personally.</p>'
        f'<div class="aferr" id="aferr{uid}">Something went wrong. Please try again or email us at <strong>info@618media.com.au</strong></div>'
        f'<div id="aform{uid}"><div class="afrow">'
        f'<div class="afg"><label class="aflbl">Name *</label><input class="afin" type="text" id="afn{uid}" placeholder="Your full name"></div>'
        f'<div class="afg"><label class="aflbl">Phone *</label><input class="afin" type="tel" id="afp{uid}" placeholder="04XX XXX XXX"></div>'
        f'</div><div class="afg"><label class="aflbl">Email *</label><input class="afin" type="email" id="afe{uid}" placeholder="you@example.com"></div>'
        f'<div class="afg"><label class="aflbl">Your question or project idea</label><textarea class="afta" id="afq{uid}" placeholder="Tell us what you are working on..."></textarea></div>'
        f'<button type="button" class="afsub" id="afsub{uid}" style="color:#ffffff !important">'
        f'<span id="afsubt{uid}">Send Message</span><span class="afspin" id="afspin{uid}"></span></button>'
        f'<p class="afpriv">A team member reviews every message personally. No automated replies.</p></div>'
        f'<div class="afconf" id="afconf{uid}"><span style="font-size:2rem;display:block;margin-bottom:.5rem">&#127916;</span>'
        f'<p><strong>Message received.</strong> The 618 Media team will get back to you personally, usually within a few hours on business days.</p></div></div>'
    )

    js = (
        f'<script>\n(function(){{\n'
        f'  var b=document.getElementById("afsub{uid}");\n'
        f'  if(!b)return;\n'
        f'  b.addEventListener("click",async function(){{\n'
        f'    var n=document.getElementById("afn{uid}").value.trim();\n'
        f'    var p=document.getElementById("afp{uid}").value.trim();\n'
        f'    var e=document.getElementById("afe{uid}").value.trim();\n'
        f'    var q=document.getElementById("afq{uid}").value.trim();\n'
        f'    var err=document.getElementById("aferr{uid}");\n'
        f'    var spin=document.getElementById("afspin{uid}");\n'
        f'    var txt=document.getElementById("afsubt{uid}");\n'
        f'    if(!n||!p||!e){{alert("Please fill in your name, phone number, and email.");return;}}\n'
        f'    b.disabled=true;txt.textContent="Sending...";spin.classList.add("on");err.classList.remove("on");\n'
        f'    try{{\n'
        f'      var r=await fetch("https://api.web3forms.com/submit",{{method:"POST",headers:{{"Content-Type":"application/json","Accept":"application/json"}},body:JSON.stringify({{"access_key":"{WEB3FORMS_KEY}","subject":"Enquiry: {article_title}","from_name":"618 Media Blog","name":n,"email":e,"phone":p,"message":"Name: "+n+"\\nPhone: "+p+"\\nEmail: "+e+"\\nArticle: {article_title}"+"\\nQuestion: "+q,"botcheck":""}})}});\n'
        f'      var d=await r.json();\n'
        f'      if(d.success){{document.getElementById("aform{uid}").style.display="none";document.getElementById("afconf{uid}").classList.add("on");}}\n'
        f'      else throw new Error(d.message||"failed");\n'
        f'    }}catch(ex){{err.classList.add("on");b.disabled=false;txt.textContent="Send Message";spin.classList.remove("on");}}\n'
        f'  }});\n'
        f'  document.querySelectorAll("#aw{uid} .afaq-btn").forEach(function(btn){{\n'
        f'    btn.addEventListener("click",function(){{\n'
        f'      var item=this.closest(".afaq-item");\n'
        f'      var isOpen=item.classList.contains("open");\n'
        f'      document.querySelectorAll("#aw{uid} .afaq-item").forEach(function(i){{i.classList.remove("open");i.querySelector(".afaq-panel").style.maxHeight="0";}});\n'
        f'      if(!isOpen){{item.classList.add("open");var panel=item.querySelector(".afaq-panel");panel.style.maxHeight=panel.scrollHeight+"px";}}\n'
        f'    }});\n'
        f'  }});\n'
        f'  var y=new Date().getFullYear().toString();\n'
        f'  document.querySelectorAll("#aw{uid} .auto-year").forEach(function(el){{el.textContent=y;}});\n'
        f'}})();\n</script>'
    )

    return (
        f'<style>\n{FULL_CSS}\n</style>\n\n'
        f'<div class="aw" id="aw{uid}">\n'
        f'  <div class="am"><span>By 618 Media</span><span>Updated <span class="auto-year">{year}</span></span><span>Sydney &amp; NSW</span></div>\n'
        f'{image_html}'
        f'  <div class="ab">\n{body}\n  </div>\n'
        f'  {table_html}\n'
        f'  {cta_html}\n'
        f'  {faq_html}\n'
        f'  {about_html}\n'
        f'  {form_html}\n'
        f'</div>\n{js}'
    )


def generate_article_html(cluster, answers, seo_title, seo_description, image_url=None, image_data=None, prompt_edits=None):
    from modules.storage import get_learning_context, get_existing_titles
    year = datetime.now().year
    uid = _uid()
    answers_text = '\n'.join(f"- {k}: {v}" for k, v in answers.items() if v)
    learning_context = get_learning_context()

    style_block = ''
    if STYLE_REFERENCE:
        style_block = (
            f"\n\nSTYLE REFERENCE — write in the same voice, structure, and quality as this article:\n"
            f"--- START REFERENCE ---\n{STYLE_REFERENCE}\n--- END REFERENCE ---\n"
            f"Match: tight sentences, specific practical advice, no filler, expert but accessible tone.\n"
        )

    learning_block = f'\n\n{learning_context}\n' if learning_context else ''

    existing_titles = get_existing_titles()
    existing_block = ''
    if existing_titles:
        recent = existing_titles[-8:]  # most recent handful — enough to steer variety without bloating the prompt
        titles_list = '\n'.join(f"- {e['seo_title']}" for e in recent if e['seo_title'])
        existing_block = (
            f"\n\nARTICLES ALREADY PUBLISHED — write something genuinely distinct from these, not just "
            f"a reworded version:\n{titles_list}\n"
            f"Do not reuse the same explanatory examples, definitions, or scaffolding these likely used "
            f"(e.g. if several already explain 'room tone' or the 'too many cooks' feedback problem, "
            f"find a different concrete example for this one). Pull genuinely different specifics — a "
            f"different pain point, a different stage of the process, a different type of client.\n"
        )

    prompt_edits_block = ''
    if prompt_edits:
        edited_parts = []
        if prompt_edits.get('angle'): edited_parts.append(f"REVISED ANGLE: {prompt_edits['angle']}")
        if prompt_edits.get('tone'): edited_parts.append(f"TONE INSTRUCTION: {prompt_edits['tone']}")
        if prompt_edits.get('extra_instructions'): edited_parts.append(f"ADDITIONAL INSTRUCTIONS: {prompt_edits['extra_instructions']}")
        if edited_parts:
            prompt_edits_block = '\n\nUSER-SPECIFIED CHANGES:\n' + '\n'.join(edited_parts) + '\n'

    prompt = (
        f"{BRAND_CONTEXT}"
        f"{style_block}"
        f"{learning_block}"
        f"{existing_block}"
        f"\n\nWrite a complete SEO article body for 618 Media. Output ONLY a JSON object.\n\n"
        f"ARTICLE DETAILS:\n"
        f"- Cluster: {cluster.get('cluster_name')}\n"
        f"- Angle: {cluster.get('article_angle')}\n"
        f"- Primary keyword: {cluster.get('primary_keyword')}\n"
        f"- Secondary keywords: {json.dumps(cluster.get('secondary_keywords', []))}\n"
        f"- PAA questions: {json.dumps(cluster.get('paa_questions', []))}\n"
        f"- SEO title: {seo_title}\n"
        f"- Copilot answers: {answers_text if answers_text else 'None'}\n"
        f"{prompt_edits_block}"
        f"\nCRITICAL HTML RULES:\n"
        f"- body contains ONLY: p, h2, h3, ul, ol, li, strong, a, div class atip\n"
        f"- NO tables, NO CTAs, NO about section, NO FAQ, NO forms, NO images in body\n"
        f"- NO h1 anywhere\n"
        f"- Pro Tip format: <div class=\"atip\"><span class=\"atip-label\">Pro Tip</span><p>...</p></div>\n"
        f"- Start body with a strong 2-3 sentence intro that hooks with a problem or counter-intuitive claim\n"
        f"- 4-6 H2 sections, at least 2 with H3 subsections\n"
        f"- One numbered factors section with H2 and H3s numbered 1 2 3\n"
        f"- One Pro Tip block\n"
        f"- THE CURRENT YEAR IS {year}. Never write 2024 or 2025\n"
        f"- Primary keyword max 3 uses total. Use semantic variants everywhere else\n"
        f"- All 20 writing rules above apply — especially: hook intro, earned headings, claims with reasons, active voice, sentence variety\n"
        f"- All FAQ answers must be fully written\n\n"
        f"Return ONLY JSON with these exact keys:\n"
        f"- body: HTML string\n"
        f"- table: object with headers, rows, footnote or null\n"
        f"- faq_items: array of q and a objects, 5-6 items\n"
        f"- slug: kebab-case URL slug max 6 words\n"
        f"- word_count: integer\n"
        f"- keywords_used: array of keywords"
    )

    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(text)

        image_html = ''
        if image_url:
            alt = seo_title.replace(' | 618 Media', '').strip()
            image_html = f'  <div class="aimg"><img src="{image_url}" alt="{alt}"></div>\n'
        elif image_data:
            alt = seo_title.replace(' | 618 Media', '').strip()
            image_html = f'  <div class="aimg"><img src="{image_data}" alt="{alt}"></div>\n'

        fragment = _assemble_html(
            uid=uid, body=result.get('body', ''),
            table_data=result.get('table'), faq_items=result.get('faq_items', []),
            seo_title=seo_title, year=year, image_html=image_html,
        )

        result['fragment'] = fragment
        result['uid'] = uid
        result['body'] = result.get('body', '')
        result['faq_items'] = result.get('faq_items', [])
        result['table'] = result.get('table')
        result['seo_title'] = seo_title
        result['seo_description'] = seo_description
        return result

    except Exception as e:
        print(f"[Generator] Article error: {e}")
        return {'error': str(e), 'fragment': '', 'slug': '', 'word_count': 0, 'keywords_used': []}


def revise_article(body, table_data, faq_items, feedback, target_section=None, cluster=None, seo_title='', image_url=None, image_data=None):
    year = datetime.now().year
    uid = _uid()

    if target_section:
        prompt = (
            f"{BRAND_CONTEXT}\n\n"
            f"Revise ONLY the section titled '{target_section}' in this article body HTML.\n"
            f"Current body:\n{body}\n\n"
            f"Feedback: {feedback}\n"
            f"THE CURRENT YEAR IS {year}. Apply all 20 writing rules.\n\n"
            f"Return ONLY JSON with: body (complete updated HTML), word_count (integer)"
        )
    else:
        prompt = (
            f"{BRAND_CONTEXT}\n\n"
            f"Revise this entire article based on the feedback below. Apply all 20 writing rules.\n\n"
            f"Current body:\n{body}\n\n"
            f"Current FAQ:\n{json.dumps(faq_items)}\n\n"
            f"Feedback: {feedback}\n"
            f"Article title: {seo_title}\n"
            f"THE CURRENT YEAR IS {year}.\n\n"
            f"Return ONLY JSON with: body (revised HTML), faq_items (array of q and a), word_count (integer)"
        )

    try:
        text = gemini(prompt).strip().replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        new_body = result.get('body', body)
        new_faq = result.get('faq_items', faq_items)

        image_html = ''
        if image_url:
            alt = seo_title.replace(' | 618 Media', '').strip()
            image_html = f'  <div class="aimg"><img src="{image_url}" alt="{alt}"></div>\n'
        elif image_data:
            alt = seo_title.replace(' | 618 Media', '').strip()
            image_html = f'  <div class="aimg"><img src="{image_data}" alt="{alt}"></div>\n'

        fragment = _assemble_html(
            uid=uid, body=new_body, table_data=table_data,
            faq_items=new_faq, seo_title=seo_title, year=year, image_html=image_html,
        )
        return {'fragment': fragment, 'body': new_body, 'faq_items': new_faq, 'uid': uid, 'word_count': result.get('word_count', 0)}
    except Exception as e:
        print(f"[Generator] Revise error: {e}")
        return {'error': str(e)}