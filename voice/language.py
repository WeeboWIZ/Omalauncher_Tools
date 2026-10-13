'''Interface languages, the text shown in them, and which language a text should be spoken in.'''
from pathlib import Path
import re

# The first is the default. The tile's language button goes through them in this order.
LANGUAGES = ('en', 'zh', 'es', 'de', 'fr', 'ja', 'ko')
CHOICE = Path.home() / '.config/omalauncher/voice-ui-language'


def chosen():
    try:
        value = CHOICE.read_text().strip()
    except OSError:
        value = ''
    return value if value in LANGUAGES else LANGUAGES[0]


# The programs write Chinese; these are the same messages in (en, es, de, fr, ja, ko).
MESSAGES = {
    '已連接，等待回覆': ('Connected, waiting for reply', 'Conectado, esperando respuesta', 'Verbunden, warte auf Antwort', 'Connecté, en attente d’une réponse', '接続済み、返信待ち', '연결됨, 응답 대기 중'),
    '已同步最近回覆': ('Latest reply synced', 'Última respuesta sincronizada', 'Letzte Antwort übernommen', 'Dernière réponse synchronisée', '最新の返信を同期しました', '최근 응답을 동기화했습니다'),
    'Codex 正在回覆…': ('Codex is working…', 'Codex está trabajando…', 'Codex arbeitet…', 'Codex travaille…', 'Codex が作業中…', 'Codex 작업 중…'),
    '收到新回覆': ('New reply received', 'Nueva respuesta recibida', 'Neue Antwort erhalten', 'Nouvelle réponse reçue', '新しい返信を受信', '새 응답 수신'),
    '已停止': ('Stopped', 'Detenido', 'Gestoppt', 'Arrêté', '停止しました', '정지됨'),
    '正在播放': ('Preparing audio', 'Preparando audio', 'Audio wird vorbereitet', 'Préparation de l’audio', '音声を準備中', '오디오 준비 중'),
    '播放完成': ('Playback complete', 'Lectura terminada', 'Wiedergabe beendet', 'Lecture terminée', '再生が完了しました', '재생 완료'),
    '播放失敗': ('Playback failed', 'La lectura falló', 'Wiedergabe fehlgeschlagen', 'Échec de la lecture', '再生に失敗しました', '재생 실패'),
    '自動播報已開啟': ('Auto-read enabled', 'Lectura automática activada', 'Automatisches Vorlesen an', 'Lecture automatique activée', '自動読み上げをオンにしました', '자동 읽기 켜짐'),
    '自動播報已關閉': ('Auto-read disabled', 'Lectura automática desactivada', 'Automatisches Vorlesen aus', 'Lecture automatique désactivée', '自動読み上げをオフにしました', '자동 읽기 꺼짐'),
    '已切換線上自然語音': ('Online voice selected', 'Voz en línea seleccionada', 'Online-Stimme gewählt', 'Voix en ligne sélectionnée', 'オンライン音声に切り替えました', '온라인 음성으로 전환'),
    '已切換離線神經語音': ('Offline voice selected', 'Voz sin conexión seleccionada', 'Offline-Stimme gewählt', 'Voix hors ligne sélectionnée', 'オフライン音声に切り替えました', '오프라인 음성으로 전환'),
    '已送到這個 Codex 會話的佇列': ('Sent to this Codex chat queue', 'Enviado a la cola de este chat de Codex', 'An die Warteschlange dieses Codex-Chats gesendet', 'Envoyé à la file de ce chat Codex', 'この Codex チャットのキューに送りました', '이 Codex 채팅 대기열로 보냈습니다'),
    '已連接終端 · 點播放讀取畫面': ('Terminal connected · tap Play to read screen', 'Terminal conectado · toca Leer para leer la pantalla', 'Terminal verbunden · Vorlesen antippen', 'Terminal connecté · touchez Lire pour lire l’écran', 'ターミナル接続済み · 再生で画面を読み上げ', '터미널 연결됨 · 재생을 눌러 화면 읽기'),
    '請在現有終端執行 tmux new -A -s oma-voice': ('Run tmux new -A -s oma-voice in your existing terminal', 'Ejecuta tmux new -A -s oma-voice en tu terminal', 'Im vorhandenen Terminal tmux new -A -s oma-voice ausführen', 'Lancez tmux new -A -s oma-voice dans votre terminal', '今のターミナルで tmux new -A -s oma-voice を実行してください', '기존 터미널에서 tmux new -A -s oma-voice 를 실행하세요'),
    '等待會話記錄': ('Waiting for chat log', 'Esperando el registro del chat', 'Warte auf Chat-Protokoll', 'En attente du journal du chat', 'チャットログを待機中', '채팅 기록 대기 중'),
    '還沒有可播放的回覆': ('No reply available to play', 'No hay respuesta para leer', 'Keine Antwort zum Vorlesen', 'Aucune réponse à lire', '再生できる返信がありません', '재생할 응답이 없습니다'),
    '找不到 Codex 會話': ('No local Codex chat found', 'No se encontró ningún chat local de Codex', 'Kein lokaler Codex-Chat gefunden', 'Aucun chat Codex local trouvé', 'ローカルの Codex チャットが見つかりません', '로컬 Codex 채팅을 찾을 수 없습니다'),
    '找不到指定會話': ('Chat not found', 'Chat no encontrado', 'Chat nicht gefunden', 'Chat introuvable', 'チャットが見つかりません', '채팅을 찾을 수 없습니다'),
    '需要 espeak-ng 和 paplay': ('espeak-ng and paplay are required', 'Se necesitan espeak-ng y paplay', 'espeak-ng und paplay werden benötigt', 'espeak-ng et paplay sont nécessaires', 'espeak-ng と paplay が必要です', 'espeak-ng 와 paplay 가 필요합니다'),
    '播放逾時': ('Playback timed out', 'La lectura tardó demasiado', 'Zeitüberschreitung bei der Wiedergabe', 'Délai de lecture dépassé', '再生がタイムアウトしました', '재생 시간 초과'),
    '請先輸入內容（最多 16000 字）': ('Enter text first (maximum 16000 characters)', 'Escribe primero un texto (máximo 16000 caracteres)', 'Zuerst Text eingeben (höchstens 16000 Zeichen)', 'Saisissez d’abord un texte (16000 caractères au plus)', '先にテキストを入力してください（最大 16000 文字）', '먼저 텍스트를 입력하세요(최대 16000자)'),
    '文字含有控制字元': ('Text contains control characters', 'El texto contiene caracteres de control', 'Der Text enthält Steuerzeichen', 'Le texte contient des caractères de contrôle', 'テキストに制御文字が含まれています', '텍스트에 제어 문자가 있습니다'),
    '送出失敗': ('Could not send text', 'No se pudo enviar el texto', 'Text konnte nicht gesendet werden', 'Impossible d’envoyer le texte', 'テキストを送信できませんでした', '텍스트를 보내지 못했습니다'),
    '未知命令': ('Unknown command', 'Comando desconocido', 'Unbekannter Befehl', 'Commande inconnue', '不明なコマンド', '알 수 없는 명령'),
    '請選 online 或 offline': ('Choose online or offline', 'Elige online u offline', 'online oder offline wählen', 'Choisissez online ou offline', 'online か offline を選んでください', 'online 또는 offline 을 고르세요'),
    '請選 Codex 或 Terminal': ('Choose codex or terminal', 'Elige codex o terminal', 'codex oder terminal wählen', 'Choisissez codex ou terminal', 'codex か terminal を選んでください', 'codex 또는 terminal 을 고르세요'),
    '請先開始語音輸入，停止後保存。': ('Start dictation, stop and save first.', 'Primero inicia el dictado, páralo y guarda.', 'Zuerst Diktat starten, stoppen und speichern.', 'Démarrez d’abord la dictée, arrêtez et enregistrez.', '先に音声入力を開始し、停止して保存してください。', '먼저 받아쓰기를 시작하고, 정지한 뒤 저장하세요.'),
    '已更新閒置暫停時間': ('Idle pause time updated', 'Tiempo de pausa actualizado', 'Leerlauf-Pause geändert', 'Délai de pause mis à jour', 'アイドル停止の時間を更新しました', '유휴 일시정지 시간을 바꿨습니다'),
    '閒置後不再暫停': ('The service no longer pauses when idle', 'El servicio ya no se pausa por inactividad', 'Der Dienst pausiert im Leerlauf nicht mehr', 'Le service ne se met plus en pause', 'アイドル時も停止しません', '유휴 시에도 일시정지하지 않습니다'),
    '請輸入 1 到 1440 的分鐘數，或 off': ('Enter 1 to 1440 minutes, or off', 'Escribe de 1 a 1440 minutos, u off', '1 bis 1440 Minuten eingeben, oder off', 'Saisissez 1 à 1440 minutes, ou off', '1〜1440 の分数、または off を入力してください', '1~1440분 또는 off 를 입력하세요'),
    '需要 tmux / tmux is required': ('tmux is required', 'Se necesita tmux', 'tmux wird benötigt', 'tmux est nécessaire', 'tmux が必要です', 'tmux 가 필요합니다'),
    '無法讀取終端畫面': ('Could not read the terminal screen', 'No se pudo leer la pantalla del terminal', 'Terminal-Bildschirm konnte nicht gelesen werden', 'Impossible de lire l’écran du terminal', 'ターミナル画面を読み取れません', '터미널 화면을 읽을 수 없습니다'),
    '無效的終端窗格': ('Invalid terminal pane', 'Panel de terminal no válido', 'Ungültiges Terminal-Fenster', 'Volet de terminal non valide', '無効なターミナルペイン', '잘못된 터미널 창'),
    '終端輸入失敗': ('Could not type into the terminal', 'No se pudo escribir en el terminal', 'Eingabe ins Terminal fehlgeschlagen', 'Impossible d’écrire dans le terminal', 'ターミナルに入力できませんでした', '터미널에 입력하지 못했습니다'),
    '請求太大': ('Request too large', 'Solicitud demasiado grande', 'Anfrage zu groß', 'Demande trop volumineuse', 'リクエストが大きすぎます', '요청이 너무 큽니다'),
    '語音服務未啟動，請查看 ~/.cache/oma-voice/daemon.log': ('The voice service did not start: see ~/.cache/oma-voice/daemon.log', 'El servicio de voz no arrancó: consulta ~/.cache/oma-voice/daemon.log', 'Der Sprachdienst ist nicht gestartet: siehe ~/.cache/oma-voice/daemon.log', 'Le service vocal n’a pas démarré : voir ~/.cache/oma-voice/daemon.log', '読み上げサービスが起動しません：~/.cache/oma-voice/daemon.log を確認', '음성 서비스가 시작되지 않았습니다: ~/.cache/oma-voice/daemon.log 확인'),
    '請選擇介面語言：': ('Choose an interface language: ', 'Elige un idioma: ', 'Sprache wählen: ', 'Choisissez une langue : ', '表示言語を選んでください：', '표시 언어를 고르세요: '),
    '完成': ('Done', 'Hecho', 'Fertig', 'Terminé', '完了', '완료'),
}
# Messages that end in a detail: 'prefix' + what follows.
PREFIXES = {
    '正在播放 · ': ('Playing · ', 'Leyendo · ', 'Wiedergabe · ', 'Lecture · ', '再生中 · ', '재생 중 · '),
    '播放完成 · ': ('Finished · ', 'Terminado · ', 'Beendet · ', 'Terminé · ', '完了 · ', '완료 · '),
    '已送到終端 · ': ('Sent to terminal · ', 'Enviado al terminal · ', 'An Terminal gesendet · ', 'Envoyé au terminal · ', 'ターミナルに送信 · ', '터미널로 보냄 · '),
}
VOICES = {
    '離線神經語音': ('offline neural', 'neuronal sin conexión', 'neuronal, offline', 'neuronale hors ligne', 'オフライン（ニューラル）', '오프라인 신경망 음성'),
    '離線基本語音': ('offline basic', 'básica sin conexión', 'einfach, offline', 'basique hors ligne', 'オフライン（基本）', '오프라인 기본 음성'),
    '自然語音（線上）': ('online natural', 'natural en línea', 'natürlich, online', 'naturelle en ligne', 'オンライン（自然）', '온라인 자연 음성'),
    '語音': ('audio', 'audio', 'Audio', 'audio', '音声', '오디오'),
}
# Why the online voice was skipped, shown beside the offline voice's name.
REASONS = {
    '線上語音未安裝': ('online voice not installed: tap Update on the tile', 'voz en línea sin instalar: toca Actualizar en el widget', 'Online-Stimme nicht installiert: im Widget Aktualisieren antippen', 'voix en ligne non installée : touchez Mettre à jour sur le widget', 'オンライン音声が未インストール：ウィジェットの更新をタップ', '온라인 음성 미설치: 위젯의 업데이트를 누르세요'),
    '缺少 mpg123': ('mpg123 missing', 'falta mpg123', 'mpg123 fehlt', 'mpg123 manquant', 'mpg123 がありません', 'mpg123 없음'),
    '線上語音無回應': ('online voice unreachable', 'voz en línea inaccesible', 'Online-Stimme nicht erreichbar', 'voix en ligne injoignable', 'オンライン音声に接続できません', '온라인 음성에 연결할 수 없음'),
}


def local(text, language=None):
    '''A message the programs wrote in Chinese, in the interface language.'''
    language = language or chosen()
    if language == 'zh' or language not in LANGUAGES:
        return text
    at = LANGUAGES.index(language) - (1 if LANGUAGES.index(language) > LANGUAGES.index('zh') else 0)
    for prefix, labels in PREFIXES.items():
        if text.startswith(prefix):
            voice, _, reason = text[len(prefix):].partition('（')
            if voice+'（'+reason in VOICES:
                return labels[at] + VOICES[voice+'（'+reason][at]
            reason = reason.rstrip('）')
            return labels[at] + (VOICES[voice][at] if voice in VOICES else voice) + (' ('+(REASONS[reason][at] if reason in REASONS else reason)+')' if reason else '')
    return MESSAGES[text][at] if text in MESSAGES else text


# Spoken notes added to a reply, in the language the reply is spoken in:
# (start of an excerpt, end of an excerpt, in place of a code block, in place of a link, the test sentence).
SPOKEN = {
    'en': ('Excerpt. ', ' Play the full reply for the rest.', ' (code omitted) ', 'link omitted', 'Voice is connected. A summary of each reply in this chat will be read aloud.'),
    'zh': ('回覆節錄。', ' 完整內容可選全文播放。', '（程式碼略過）', '連結略過', '語音播報已連接。之後會自動播放這個對話的回覆摘要。'),
    'es': ('Extracto. ', ' Reproduce la respuesta completa para oír el resto.', ' (código omitido) ', 'enlace omitido', 'La voz está conectada. Se leerá un resumen de cada respuesta de este chat.'),
    'de': ('Auszug. ', ' Für den Rest die ganze Antwort abspielen.', ' (Code ausgelassen) ', 'Link ausgelassen', 'Die Stimme ist verbunden. Von jeder Antwort in diesem Chat wird eine Kurzfassung vorgelesen.'),
    'fr': ('Extrait. ', ' Lisez la réponse entière pour la suite.', ' (code omis) ', 'lien omis', 'La voix est connectée. Un résumé de chaque réponse de ce chat sera lu.'),
    'ja': ('返信の抜粋です。', ' 続きは全文再生で聞けます。', '（コードは省略）', 'リンク省略', '音声読み上げに接続しました。このチャットの返信の要約を読み上げます。'),
    'ko': ('응답 발췌입니다. ', ' 나머지는 전체 재생으로 들을 수 있습니다.', ' (코드 생략) ', '링크 생략', '음성 읽기가 연결되었습니다. 이 채팅의 응답 요약을 읽어 드립니다.'),
}

# Common words that tell the four Latin-script languages apart.
WORDS = {
    'en': 'the and is are of to that this with for you not it was have be on as at by from or an will can',
    'es': 'el la los las que de y en es un una por con para no se lo como más pero sus le ya o fue este sí porque',
    'de': 'der die das und ist nicht ein eine mit für auf den zu von ich sie es dem des im auch sich als wird noch',
    'fr': 'le la les des est et un une pour dans que qui pas sur avec ce il au du en ne se plus par je sont cette',
}
WORDS = {code: set(words.split()) for code, words in WORDS.items()}


def spoken(text, interface=None):
    '''The language to read a text in: by its script, then by its words, then the interface language.'''
    interface = interface or chosen()
    han = sum('㐀' <= c <= '鿿' for c in text)
    kana = sum('぀' <= c <= 'ヿ' for c in text)
    hangul = sum('가' <= c <= '힣' for c in text)
    if kana and kana * 10 >= han:
        return 'ja'
    if hangul and hangul >= han:
        return 'ko'
    if han:
        return 'zh'
    found = re.findall(r"[^\W\d_]+", text.lower())
    counts = {code: sum(word in words for word in found) for code, words in WORDS.items()}
    best = max(counts, key=counts.get)
    ahead = sorted(counts.values())[-1] - sorted(counts.values())[-2]
    if counts[best] >= 3 and ahead >= 2:
        return best
    return interface if interface in WORDS else 'en'
