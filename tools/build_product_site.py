"""Build the static product page from concise three-language copy and native captures."""
from pathlib import Path
import html
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'website' / 'dist'
REPO = 'https://github.com/1zhiguo/sinisistar2-dglab-control-center'

def main():
    (OUT/'assets/screens').mkdir(parents=True, exist_ok=True)
    from PIL import Image
    for name in ('overview','devices','quick','strategy','waveforms'):
        with Image.open(ROOT/f'artifacts/website-capture/{name}.png') as im:
            im.convert('RGB').save(OUT/f'assets/screens/{name}.webp', quality=90)
    if not (OUT/'assets/game-icon.svg').is_file():
        raise FileNotFoundError('Build the square game icon with tools/build_game_icon.py first')
    reference_assets=ROOT.parent/'Ricca-x-DGlab/website/dist/assets'
    for name in ('x-avatar.png','qq-group.jpg','reward-code.jpg','dglab-icon.png'):
        if not (OUT/'assets'/name).is_file() and (reference_assets/name).is_file():
            shutil.copyfile(reference_assets/name,OUT/'assets'/name)
        elif not (OUT/'assets'/name).is_file():
            raise FileNotFoundError(f'Missing shared support asset: {name}')
    copy = {}
    def text(key, zh, en, ja, tag='span', attrs=''):
        copy[key] = {'zh':zh, 'en':en, 'ja':ja}
        return f'<{tag} data-i18n="{key}" {attrs}>{html.escape(zh)}</{tag}>'
    t=text
    features = [
        ('受伤与战败反馈','Damage and defeat feedback','ダメージ・敗北フィードバック','按受伤、异常和已验证的战败流程设置强度、波形与时长。','Set intensity, waves and duration for damage, status effects and verified defeat flows.','ダメージ、状態異常、確認済みの敗北イベントごとに強度・波形・時間を設定。'),
        ('V3 / V4 双设备连接','V3 / V4 device pairing','V3 / V4 デバイス接続','支持郊狼与负鼠；两种设备及 A/B 通道独立配置。','Connect Coyote and Opossum with separate device and A/B channel settings.','郊狼と負鼠に対応。デバイスと A/B チャンネルを個別に設定。'),
        ('低 / 中 / 高预设','Low / medium / high presets','低・中・高プリセット','快速选择档位，或分别调整强度、上限和反馈时长。','Choose a preset or adjust intensity, caps and feedback duration.','プリセットを選択し、強度・上限・フィードバック時間を調整。'),
        ('波形工作台','Waveform studio','波形エディター','拖绘波形，预览预设，支持撤销、重做和自定义保存。','Draw waves, preview presets, undo, redo and save custom patterns.','波形の描画、プリセットのプレビュー、元に戻す・やり直し・保存に対応。'),
        ('四通道游戏 HUD','Four-channel game HUD','4 チャンネル HUD','显示 Pulse / 负鼠 A/B 输出，位置、缩放和透明度可调。','View Pulse and Opossum A/B output; adjust position, scale and opacity.','Pulse・負鼠の A/B 出力を表示。位置・サイズ・透明度を調整可能。'),
        ('CG 反馈与波形队列','CG feedback and wave queues','CG フィードバック・波形キュー','独立设置 CG 反馈和分段波形的顺序、强度与时长。','Configure CG feedback and the order, intensity and timing of wave segments.','CG のフィードバックと波形の順番・強度・時間を個別設定。'),
        ('事件检测器','Event inspector','イベントモニター','查看 HP / MP、当前异常和游戏事件，支持独立窗口。','Inspect HP / MP, active status effects and game events in a detachable window.','HP・MP、現在の状態異常、ゲームイベントを確認。別ウィンドウ表示に対応。'),
        ('全局急停','Global emergency stop','グローバル緊急停止','默认 Ctrl+F12，归零并锁定两路输出；支持自定义按键。','Ctrl+F12 zeros and locks both output routes. The shortcut is configurable.','標準は Ctrl+F12。両方の出力をゼロにしてロック。キーの変更も可能。')]
    cards=''.join(f'<article><span class="feature-number">{i+1:02}</span><div>'+t(f'f{i}h',*f[:3],tag='h3')+t(f'f{i}p',*f[3:],tag='p')+'</div></article>' for i,f in enumerate(features))
    screens=[]
    for key,zh,en,ja in [
        ('devices','设备与游戏 · 插件安装、扫码与设备连接','Devices & game · plugin installation and pairing','デバイス・ゲーム · プラグイン導入と接続'),
        ('quick','快速设置 · 预设与独立 A/B 强度','Quick settings · presets and independent A/B levels','クイック設定 · プリセットと A/B 強度'),
        ('strategy','联动策略 · 事件、波形与反馈时长','Feedback rules · events, waves and duration','連動ルール · イベント・波形・時間'),
        ('waveforms','波形工作台 · 拖绘、预览与保存','Waveform studio · draw, preview and save','波形エディター · 描画・プレビュー・保存')]:
        screens.append(f'<figure><button class="screenshot" type="button" data-image="assets/screens/{key}.webp" aria-label="'+html.escape(en)+'"><img src="assets/screens/'+key+'.webp" alt="'+html.escape(en)+'" loading="lazy" width="1800" height="1175"></button>'+t('screen'+key,zh,en,ja,tag='figcaption')+'</figure>')
    steps=[]
    for i,f in enumerate([
        ('运行控制中心','Run the control center','コントロールセンターを起動','下载源码，安装 requirements-native.txt 后运行 run_native.cmd。','Download the source, install requirements-native.txt, then run run_native.cmd.','ソースをダウンロードし、requirements-native.txt を導入して run_native.cmd を実行。'),
        ('安装游戏插件','Install the game plugin','ゲームプラグインを導入','在「设备与游戏」选择 v1.3.1 游戏目录，安装联动插件后启动游戏。','Select the v1.3.1 game folder in Devices & game, install the plugin, then launch the game.','「デバイス・ゲーム」で v1.3.1 のフォルダーを選択。プラグイン導入後にゲームを起動。'),
        ('扫码与设置','Pair and configure','接続と設定','手机与电脑接入同一局域网，选择 V3 / V4 扫码，确认设备、预设与上限。','Use the same LAN on phone and PC. Pair through V3 / V4, then check devices, presets and caps.','スマートフォンと PC を同じ LAN に接続。V3 / V4 で QR 接続し、デバイス・プリセット・上限を確認。')]):
        steps.append(f'<li><b>0{i+1}</b><div>'+t(f'step{i}h',*f[:3],tag='h3')+t(f'step{i}p',*f[3:],tag='p')+'</div></li>')
    page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#11100e"><meta name="description" content="SiNiSistar2 × DG-LAB：V3 / V4 郊狼与负鼠连接、事件联动、波形编辑和游戏 HUD。"><title>SiNiSistar2 × DG-LAB</title><link rel="canonical" href="https://sinisistar2-dglab.web.app/"><link rel="icon" href="assets/game-icon.svg"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="support.css"><link rel="stylesheet" href="gothic.css"><link rel="stylesheet" href="brand-lockup.css"><script src="site.js" defer></script></head><body>'''
    page+=t('skip','跳到正文','Skip to content','本文へ',tag='a',attrs='class="skip" href="#main"')
    page+='<header class="shell"><div class="header-top">'+t('back','← 返回 DG-LAB × Any','← Back to DG-LAB × Any','← DG-LAB × Any に戻る',tag='a',attrs='href="https://dglab-x-game.web.app/"')+f'<div class="tools"><a href="{REPO}">GitHub ↗</a><select id="language" aria-label="Language / 语言 / 言語"><option value="zh">中文</option><option value="en">English</option><option value="ja">日本語</option></select></div></div><div class="header-main"><a class="brand" href="#top"><img src="assets/game-icon.svg" alt="" width="36" height="36">SiNiSistar2 × DG-LAB</a><nav aria-label="Navigation">'
    for key,zh,en,ja,anchor in [('navf','功能','Features','機能','features'),('navs','界面','Interface','画面','screens'),('navg','使用说明','Setup','使い方','setup'),('navd','下载','Download','ダウンロード','download')]:page+=t(key,zh,en,ja,tag='a',attrs=f'href="#{anchor}"')
    page+='</nav></div></header><main id="main"><section class="hero shell" id="top"><p class="eyebrow">WINDOWS · DG-LAB V3 / V4 · PULSE / OPOSSUM</p><div class="hero-heading"><h1>SiNiSistar2 <span>× DG-LAB</span></h1><div>'+t('subtitle','控制中心','Control Center','コントロールセンター',tag='h2')+t('lead','将受伤、异常状态和战败流程同步到郊狼与负鼠。独立设置通道、强度、波形与时长。','Sync damage, status effects and defeat flows with Coyote and Opossum. Configure channels, intensity, waves and duration independently.','ダメージ・状態異常・敗北イベントを郊狼と負鼠に連動。チャンネル・強度・波形・時間を個別に設定。',tag='p',attrs='class="lead"')+'</div></div><div class="hero-actions">'+t('get','获取源码','Get the source','ソースを入手',tag='a',attrs='class="button primary" href="#download"')+t('start','查看使用步骤 ↗','Setup steps ↗','導入手順 ↗',tag='a',attrs='class="button" href="#setup"')+t('compat','SiNiSistar2 v1.3.1 · 中 / 英 / 日界面','SiNiSistar2 v1.3.1 · Chinese / English / Japanese UI','SiNiSistar2 v1.3.1 · 中国語・英語・日本語 UI',tag='p',attrs='class="muted"')+'</div><figure class="hero-screen"><button class="screenshot" type="button" data-image="assets/screens/overview.webp" aria-label="Overview screenshot"><img src="assets/screens/overview.webp" alt="SiNiSistar2 control center overview" width="1800" height="1175" fetchpriority="high"></button>'+t('capture','软件实际界面 · 离线截图，设备未连接','Actual application · offline captures, devices disconnected','実際のソフトウェア画面 · オフライン撮影、デバイス未接続',tag='figcaption')+'</figure></section>'
    page+='<section id="features" class="section shell"><div class="section-title"><p class="eyebrow">01 / FEATURES</p>'+t('features','核心功能','Core features','主な機能',tag='h2')+'</div><div class="features">'+cards+'</div></section>'
    page+='<section id="screens" class="section shell"><div class="section-title"><p class="eyebrow">02 / INTERFACE</p>'+t('screens','程序界面','Application interface','ソフトウェア画面',tag='h2')+t('expand','点击截图可放大查看。','Select a screenshot to enlarge.','画像をクリックして拡大。',tag='p')+'</div><div class="screens">'+''.join(screens)+'</div></section>'
    page+='<section id="setup" class="section shell"><div class="section-title"><p class="eyebrow">03 / SETUP</p>'+t('setup','使用步骤','Setup','導入手順',tag='h2')+'</div><ol class="steps">'+''.join(steps)+'</ol>'+t('prereq','源码运行需要 Windows x64、Python 3.10+。首次安装游戏插件前退出游戏；连接后按软件内五步教程设置。','Source setup requires Windows x64 and Python 3.10+. Close the game before installing its plugin. Follow the five-step tutorial in the app.','ソース実行には Windows x64 と Python 3.10+ が必要です。プラグイン導入前にゲームを終了し、アプリ内の 5 ステップガイドに従ってください。',tag='p',attrs='class="note"')+'</section>'
    page+='<section id="download" class="section shell"><div class="section-title"><p class="eyebrow">04 / SOURCE</p>'+t('download','下载与源码','Download & source','ダウンロード・ソース',tag='h2')+'</div><div class="download-panel"><div>'+t('version','开发版 · 0.6','Development build · 0.6','開発版 · 0.6',tag='h3')+t('sourcebody','提供原生界面、观察插件与独立辅助插件源码。运行时和插件构建步骤见仓库说明。','Includes source for the native UI, observer and optional helper plugin. See the repository for runtime setup and plugin builds.','ネイティブ UI、観測プラグイン、任意の補助プラグインのソースを公開。ランタイムの準備とビルド方法はリポジトリに記載。',tag='p')+t('sourcenote','下载内容为源码 ZIP，需要安装 Python 依赖；不含游戏本体和运行时二进制。','This is a source ZIP requiring Python dependencies. Game files and runtime binaries are not included.','Python の依存パッケージが必要なソース ZIP です。ゲーム本体とランタイムのバイナリは含みません。',tag='p',attrs='class="muted"')+'</div><div class="download-actions">'+t('zip','下载源码 ZIP ↓','Download source ZIP ↓','ソース ZIP をダウンロード ↓',tag='a',attrs=f'class="button primary" href="{REPO}/archive/refs/heads/main.zip"')+t('github','查看 GitHub ↗','View on GitHub ↗','GitHub を開く ↗',tag='a',attrs=f'class="button" href="{REPO}"')+'</div></div></section>'
    page+='</main><footer class="shell">'+t('rights','非官方联动工具，不包含游戏本体。游戏画面、角色与 DG-LAB 标识归各自权利人所有；项目代码采用 GPL-3.0。','Unofficial companion; the game is not included. Game artwork, characters and DG-LAB marks belong to their owners. Project code is GPL-3.0.','非公式の連動ツール。ゲーム本体は含みません。ゲーム画像・キャラクター・DG-LAB の標章は各権利者に帰属。コードは GPL-3.0。',tag='p')+'<div><a href="https://dglab-x-game.web.app/">DG-LAB × Any ↗</a><a href="https://x.com/1zhiguo">X · @1zhiguo ↗</a></div></footer><dialog id="lightbox" aria-label="Screenshot"><button id="close-image" type="button" aria-label="Close / 关闭 / 閉じる">×</button><img alt=""></dialog></body></html>'
    support='<section id="support" class="section shell"><div class="section-title"><p class="eyebrow">05 / SUPPORT</p>'+t('support','支持与交流','Support & community','サポート・コミュニティ',tag='h2')+'</div>'
    support+='<article class="social-profile"><img class="social-avatar" src="assets/x-avatar.png" alt="Guoguo" width="96" height="96" loading="lazy"><div><h3>X · @1zhiguo</h3>'+t('socialcopy','开发动态与版本更新','Development updates and releases','開発情報・バージョン更新',tag='p')+'</div>'+t('socialfollow','在 X 上关注 ↗','Follow on X ↗','X でフォロー ↗',tag='a',attrs='class="button" href="https://x.com/1zhiguo" target="_blank" rel="noopener noreferrer"')+'</article>'
    support+='<div class="support-grid"><article>'+t('community','技术交流群','Community chat','コミュニティ',tag='h3')+t('groupnumber','QQ群：1129729751','QQ group: 1129729751','QQ グループ：1129729751',tag='p')+'<button type="button" class="screenshot support-code" data-image="assets/qq-group.jpg?v=20261027-any" aria-label="Enlarge QQ group QR code"><img src="assets/qq-group.jpg?v=20261027-any" alt="QQ group 1129729751 QR code" width="1284" height="2283" loading="lazy"></button></article><article>'+t('reward','赞赏项目','Support the project','プロジェクトを支援',tag='h3')+t('rewardcode','赞赏码','Reward code','支援用 QR コード',tag='p')+'<button type="button" class="screenshot support-code" data-image="assets/reward-code.jpg" aria-label="Enlarge reward QR code"><img src="assets/reward-code.jpg" alt="Guoguo reward QR code" width="1152" height="1152" loading="lazy"></button></article></div>'+t('qrenlarge','点击二维码可放大查看。','Select a QR code to enlarge.','QR コードをクリックして拡大。',tag='p',attrs='class="muted"')+'</section>'
    page=page.replace('</main><footer',support+'</main><footer',1)
    lockup='<div class="hero-brand-lockup" role="img" aria-label="DG-LAB × SiNiSistar2"><span class="partner-mark dglab-mark"><img src="assets/dglab-icon.png" alt="" width="104" height="104"></span><span class="partner-cross" aria-hidden="true">×</span><span class="partner-mark game-mark"><img src="assets/game-icon.svg" alt="" width="104" height="104"></span></div>'
    page=page.replace('</h1><div>','</h1><div>'+lockup,1)
    (OUT/'index.html').write_text(page,encoding='utf-8')
    (OUT/'translations.json').write_text(json.dumps(copy,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Built product site: {len(copy)} translated labels, 5 native screenshots')

if __name__=='__main__':main()
