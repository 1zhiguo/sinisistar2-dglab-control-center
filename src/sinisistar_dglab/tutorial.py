"""Five essential setup steps; navigation never enables device output."""
TUTORIAL_VERSION=2
STEPS=[
    (1,('选择目录，安装插件','Choose a folder and install','フォルダー選択と導入'),
     ('选择包含 SiNiSistar2.exe 的游戏目录，点击“安装 / 修复环境”。安装完成后启动游戏。',
      'Choose the game folder containing SiNiSistar2.exe, then select Install / repair runtime. Start the game after installation.',
      'SiNiSistar2.exeを含むゲームフォルダーを選び、「導入 / 実行環境の修復」を押します。導入後にゲームを起動します。')),
    (1,('选择 V3 / V4，连接郊狼','Choose V3 / V4 and connect','V3 / V4を選んで接続'),
     ('选择 V3 或 V4，点击“启动扫码连接”，再用对应的 DG-LAB APP 扫码。手机与电脑需连接同一局域网。',
      'Choose V3 or V4, start QR pairing, then scan with the matching DG-LAB APP. Keep your phone and PC on the same LAN.',
      'V3またはV4を選んでQR接続を開始し、対応するDG-LAB APPで読み取ります。スマートフォンとPCは同じLANに接続します。')),
    (1,('启用 Pulse','Enable Pulse','Pulseを有効にする'),
     ('连接就绪后点击右上角“启动 Pulse”。显示“暂停 Pulse”时即已启用；无法启用时按设备卡片里的提示处理。',
      'When connected, select Start Pulse at the top right. Pause Pulse means output is enabled. If unavailable, follow the device card guidance.',
      '接続の準備ができたら右上の「Pulseを開始」を押します。「Pulseを停止」の表示なら有効です。押せない場合はデバイス欄の案内を確認します。')),
    (2,('快捷选择预设','Choose an intensity preset','強度プリセットを選ぶ'),
     ('在“预设强度”中选择低、中或高。更改预设后输出会暂停，确认强度后再次启动 Pulse。',
      'Choose Low, Medium or High under Intensity presets. Changing the preset pauses output; check the intensity and start Pulse again.',
      '強度プリセットで低・中・高を選びます。変更すると出力が一時停止するので、強度を確認してからPulseを再開します。')),
    (2,('打开 HUD，调整位置','Show and position the HUD','HUDを表示して配置'),
     ('打开顶部 HUD 开关。点“调整 HUD 位置”，拖动 HUD 放到合适位置，再点“完成 / 锁定”。完成后即可开始游玩。',
      'Turn on HUD at the top. Select Adjust HUD position, drag it into place, then choose Done / lock. You are ready to play.',
      '上部のHUDをオンにします。「HUDの位置調整」を押してドラッグで配置し、「完了 / ロック」を押します。これで準備完了です。')),
]
STEP_COUNT=len(STEPS)

def steps(language):
    index={'zh-CN':0,'en':1,'ja':2}.get(language,0)
    return [dict(page=page,title=title[index],body=body[index]) for page,title,body in STEPS]
