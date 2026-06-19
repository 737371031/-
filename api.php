<?php
declare(strict_types=1);

session_set_cookie_params([
    'lifetime' => 0,
    'path' => '/',
    'httponly' => true,
    'samesite' => 'Lax',
    'secure' => (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off'),
]);
session_start();

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

$baseDir = __DIR__;
$modelsFile = $baseDir . DIRECTORY_SEPARATOR . 'models.json';
$configFile = $baseDir . DIRECTORY_SEPARATOR . 'model-admin-config.php';

function respond(array $payload, int $status = 200): void
{
    http_response_code($status);
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function read_json_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') {
        return [];
    }

    $data = json_decode($raw, true);
    if (!is_array($data)) {
        respond(['ok' => false, 'message' => '请求 JSON 格式不正确'], 400);
    }

    return $data;
}

function config_exists(string $configFile): bool
{
    return is_file($configFile);
}

function load_config(string $configFile): array
{
    if (!config_exists($configFile)) {
        return [];
    }

    $config = require $configFile;
    return is_array($config) ? $config : [];
}

function require_login(): void
{
    if (empty($_SESSION['model_admin_logged_in'])) {
        respond(['ok' => false, 'message' => '请先登录'], 401);
    }
}

function write_file_locked(string $path, string $content): void
{
    $dir = dirname($path);
    if (!is_writable($dir)) {
        respond(['ok' => false, 'message' => '当前目录不可写，请检查服务器权限'], 500);
    }

    $lockPath = $path . '.lock';
    $lock = fopen($lockPath, 'c');
    if (!$lock) {
        respond(['ok' => false, 'message' => '无法创建写入锁文件'], 500);
    }

    try {
        if (!flock($lock, LOCK_EX)) {
            respond(['ok' => false, 'message' => '无法锁定文件'], 500);
        }

        $tmpPath = $path . '.tmp';
        if (file_put_contents($tmpPath, $content, LOCK_EX) === false) {
            respond(['ok' => false, 'message' => '写入临时文件失败'], 500);
        }

        if (!rename($tmpPath, $path)) {
            @unlink($tmpPath);
            respond(['ok' => false, 'message' => '替换数据文件失败'], 500);
        }

        @chmod($path, 0644);
        flock($lock, LOCK_UN);
    } finally {
        fclose($lock);
    }
}

function normalize_catalog(array $catalog): array
{
    $title = trim((string)($catalog['title'] ?? '模型服务目录'));
    $updatedAt = trim((string)($catalog['updatedAt'] ?? date('Y-m-d')));
    $models = $catalog['models'] ?? null;

    if ($title === '') {
        respond(['ok' => false, 'message' => '目录标题不能为空'], 422);
    }
    if (!is_array($models)) {
        respond(['ok' => false, 'message' => 'models 必须是数组'], 422);
    }

    $allowedTypes = ['text', 'image', 'embed', 'audio', 'video'];
    $allowedStatuses = ['ready', 'beta', 'offline'];
    $normalized = [];
    $ids = [];

    foreach ($models as $index => $model) {
        if (!is_array($model)) {
            respond(['ok' => false, 'message' => '第 ' . ($index + 1) . ' 个模型格式不正确'], 422);
        }

        $name = trim((string)($model['name'] ?? ''));
        $id = trim((string)($model['id'] ?? ''));
        $provider = trim((string)($model['provider'] ?? ''));
        $type = trim((string)($model['type'] ?? 'text'));
        $context = trim((string)($model['context'] ?? ''));
        $price = trim((string)($model['price'] ?? ''));
        $status = trim((string)($model['status'] ?? 'ready'));
        $description = trim((string)($model['description'] ?? ''));

        if ($name === '' || $id === '') {
            respond(['ok' => false, 'message' => '第 ' . ($index + 1) . ' 个模型缺少名称或 ID'], 422);
        }
        if (isset($ids[$id])) {
            respond(['ok' => false, 'message' => '模型 ID 重复：' . $id], 422);
        }
        if (!in_array($type, $allowedTypes, true)) {
            respond(['ok' => false, 'message' => '模型类型不支持：' . $type], 422);
        }
        if (!in_array($status, $allowedStatuses, true)) {
            respond(['ok' => false, 'message' => '模型状态不支持：' . $status], 422);
        }

        $ids[$id] = true;
        $normalized[] = [
            'name' => $name,
            'id' => $id,
            'provider' => $provider,
            'type' => $type,
            'context' => $context,
            'price' => $price,
            'status' => $status,
            'description' => $description,
        ];
    }

    return [
        'title' => $title,
        'updatedAt' => $updatedAt,
        'models' => $normalized,
    ];
}

$action = (string)($_GET['action'] ?? '');

if ($_SERVER['REQUEST_METHOD'] === 'GET' && $action === 'status') {
    respond([
        'ok' => true,
        'configured' => config_exists($configFile),
        'authenticated' => !empty($_SESSION['model_admin_logged_in']),
        'canWriteModels' => is_writable($modelsFile) || (!is_file($modelsFile) && is_writable($baseDir)),
        'canWriteConfig' => config_exists($configFile) ? is_writable($configFile) : is_writable($baseDir),
    ]);
}

if ($_SERVER['REQUEST_METHOD'] === 'GET' && $action === 'load') {
    if (!is_file($modelsFile)) {
        respond(['ok' => true, 'catalog' => ['title' => '模型服务目录', 'updatedAt' => date('Y-m-d'), 'models' => []]]);
    }

    $json = file_get_contents($modelsFile);
    $catalog = json_decode((string)$json, true);
    if (!is_array($catalog)) {
        respond(['ok' => false, 'message' => 'models.json 解析失败'], 500);
    }

    respond(['ok' => true, 'catalog' => $catalog]);
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    respond(['ok' => false, 'message' => '不支持的请求'], 405);
}

$body = read_json_body();

if ($action === 'setup') {
    if (config_exists($configFile)) {
        respond(['ok' => false, 'message' => '管理员密码已经设置'], 409);
    }

    $password = (string)($body['password'] ?? '');
    if (strlen($password) < 8) {
        respond(['ok' => false, 'message' => '密码至少 8 位'], 422);
    }

    $hash = password_hash($password, PASSWORD_DEFAULT);
    $config = "<?php\nreturn [\n    'password_hash' => " . var_export($hash, true) . ",\n];\n";
    write_file_locked($configFile, $config);
    $_SESSION['model_admin_logged_in'] = true;
    respond(['ok' => true, 'message' => '管理员密码已设置']);
}

if ($action === 'login') {
    $config = load_config($configFile);
    if (empty($config['password_hash'])) {
        respond(['ok' => false, 'message' => '请先设置管理员密码'], 428);
    }

    $password = (string)($body['password'] ?? '');
    if (!password_verify($password, (string)$config['password_hash'])) {
        respond(['ok' => false, 'message' => '密码不正确'], 401);
    }

    $_SESSION['model_admin_logged_in'] = true;
    respond(['ok' => true, 'message' => '登录成功']);
}

if ($action === 'logout') {
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $params = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $params['path'], $params['domain'] ?? '', (bool)$params['secure'], (bool)$params['httponly']);
    }
    session_destroy();
    respond(['ok' => true, 'message' => '已退出']);
}

if ($action === 'save') {
    require_login();
    $catalog = normalize_catalog($body['catalog'] ?? []);
    $json = json_encode($catalog, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($json === false) {
        respond(['ok' => false, 'message' => '生成 JSON 失败'], 500);
    }

    write_file_locked($modelsFile, $json . "\n");
    respond(['ok' => true, 'message' => '保存成功', 'catalog' => $catalog]);
}

respond(['ok' => false, 'message' => '未知操作'], 404);
