"""
hou を使って hip の中身を調べたり変更したりする関数群（hython で動かす）

どの関数も JSON にそのまま変換できる dict / list を返す。
HTTP のことは知らない。HTTP との橋渡しは server/handlers.py が行う。
"""
import os
import string
import time

import hou

HIP_EXTS = (".hip", ".hipnc", ".hiplc")
SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")

# ROP の出力先を表すことが多いパラメータ名
OUTPUT_PARMS = ("lopoutput", "sopoutput", "picture", "vm_picture", "ar_picture",
                "copoutput", "outputfile", "file")

# 表示しないパラメータの種類（フォルダや見出しなど、値を持たないもの）
_SKIP_PARM_TYPES = (
    hou.parmTemplateType.Folder,
    hou.parmTemplateType.FolderSet,
    hou.parmTemplateType.Separator,
    hou.parmTemplateType.Label,
)


class HipError(Exception):
    """利用者に見せるエラー。status は HTTP のステータスコード"""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# このツールで変更してから、まだ保存していないか
# （hou.hipFile.hasUnsavedChanges() は読み込んだ直後でも True になることがあるので自前で持つ）
_unsaved = False


# --- hip ファイル -----------------------------------------------------------

def status():
    path = hou.hipFile.path()
    return {
        "hipPath": path,
        "hipName": os.path.basename(path),
        "isNewFile": hou.hipFile.isNewFile(),
        "unsaved": _unsaved,
        "houdini": hou.applicationVersionString(),
        "license": hou.licenseCategory().name(),
        "samplesDir": SAMPLES_DIR,
    }


def open_hip(path):
    global _unsaved
    path = os.path.abspath(os.path.expandvars(path))
    if not os.path.isfile(path):
        raise HipError(f"ファイルがありません: {path}", 404)
    if not path.lower().endswith(HIP_EXTS):
        raise HipError(f"hip ファイルではありません: {path}")
    # 読み込みの警告（足りないプラグインなど）では止めない
    hou.hipFile.load(path.replace("\\", "/"), suppress_save_prompt=True,
                     ignore_load_warnings=True)
    _unsaved = False
    return status()


def save_hip(path=None):
    global _unsaved
    if path:
        path = os.path.abspath(os.path.expandvars(path))
        if not path.lower().endswith(HIP_EXTS):
            raise HipError(f"拡張子は {', '.join(HIP_EXTS)} のどれかにしてください")
        hou.hipFile.save(path.replace("\\", "/"))
    else:
        if hou.hipFile.isNewFile():
            raise HipError("まだ保存先が決まっていません。別名で保存してください")
        hou.hipFile.save()
    _unsaved = False
    return status()


def list_files(directory):
    """フォルダの中のサブフォルダと hip ファイルを返す。空文字ならドライブ一覧"""
    if not directory:
        drives = [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
        return {"dir": "", "parent": None, "dirs": drives, "files": []}

    directory = os.path.abspath(os.path.expandvars(directory))
    if not os.path.isdir(directory):
        raise HipError(f"フォルダがありません: {directory}", 404)

    dirs, files = [], []
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())
    except PermissionError:
        raise HipError(f"フォルダを開けません: {directory}", 403)
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if entry.is_dir():
                dirs.append(entry.name)
            elif entry.name.lower().endswith(HIP_EXTS):
                files.append(entry.name)
        except OSError:
            continue

    parent = os.path.dirname(directory)
    return {
        "dir": directory,
        # ドライブのルートでは、親としてドライブ一覧（空文字）を返す
        "parent": "" if parent == directory else parent,
        "dirs": dirs,
        "files": files,
    }


# --- ノード -----------------------------------------------------------------

def _get_node(path):
    node = hou.node(path) if path else None
    if node is None:
        raise HipError(f"ノードがありません: {path}", 404)
    return node


def _flag(node, method):
    func = getattr(node, method, None)
    if func is None:
        return None
    try:
        return func()
    except hou.Error:
        return None


def _node_summary(node):
    node_type = node.type()
    parent = node.parent()
    inputs = []
    for conn in node.inputConnections():
        src = conn.inputNode()
        # サブネットの入力など、同じネットワークの外から来る接続は描かない
        if src is None or src.parent() != parent:
            continue
        inputs.append({
            "from": src.path(),
            "fromIndex": conn.outputIndex(),
            "toIndex": conn.inputIndex(),
        })

    pos = node.position()
    size = node.size()
    return {
        "path": node.path(),
        "name": node.name(),
        "type": node_type.name(),
        "typeLabel": node_type.description(),
        "category": node_type.category().name(),
        "hasChildren": len(node.children()) > 0,
        "isRop": isinstance(node, hou.RopNode),
        "position": [pos[0], pos[1]],
        "size": [size[0], size[1]],
        "color": list(node.color().rgb()),
        "maxInputs": min(node_type.maxNumInputs(), 8),
        "maxOutputs": min(node_type.maxNumOutputs(), 8),
        "inputs": inputs,
        "flags": {
            "display": _flag(node, "isDisplayFlagSet"),
            "render": _flag(node, "isRenderFlagSet"),
            "template": _flag(node, "isTemplateFlagSet"),
            "bypass": _flag(node, "isBypassed"),
        },
        "errors": len(node.errors()),
        "warnings": len(node.warnings()),
    }


def list_nodes(path):
    """ノードの子ノードと、そのつながりを返す"""
    node = _get_node(path or "/")
    parent = node.parent()
    return {
        "path": node.path(),
        "parent": parent.path() if parent is not None else None,
        "children": [_node_summary(child) for child in node.children()],
    }


# --- パラメータ -------------------------------------------------------------

def _parm_type_name(template):
    t = template.type()
    if t == hou.parmTemplateType.Float:
        return "float"
    if t == hou.parmTemplateType.Int:
        return "int"
    if t == hou.parmTemplateType.String:
        return "string"
    if t == hou.parmTemplateType.Toggle:
        return "toggle"
    if t == hou.parmTemplateType.Menu:
        return "menu"
    if t == hou.parmTemplateType.Button:
        return "button"
    if t == hou.parmTemplateType.Ramp:
        return "ramp"
    return "other"


def _parm_value(parm, kind):
    if kind in ("ramp", "button", "other"):
        return None
    if kind == "menu":
        return parm.evalAsString()
    if kind == "toggle":
        return bool(parm.eval())
    return parm.eval()


def _parm_raw(parm, kind):
    """エクスプレッションやアニメーションが付いているときの元の式。なければ None"""
    if parm.keyframes():
        try:
            return parm.expression()
        except hou.OperationFailed:
            return "(アニメーション)"
    if kind == "string":
        raw = parm.unexpandedString()
        # $HIP など、評価で中身が変わるときだけ返す
        return raw if raw != parm.eval() else None
    return None


def _parm_menu(parm, template):
    try:
        items = parm.menuItems()
        labels = parm.menuLabels()
    except hou.Error:
        return None
    if not items:
        return None
    return [{"value": v, "label": l} for v, l in zip(items, labels)]


def node_parms(path):
    node = _get_node(path)
    parms = []
    for pt in node.parmTuples():
        template = pt.parmTemplate()
        if template.type() in _SKIP_PARM_TYPES:
            continue
        kind = _parm_type_name(template)
        components = []
        for parm in pt:
            raw = _parm_raw(parm, kind)
            components.append({
                "value": _parm_value(parm, kind),
                "raw": raw,
                "locked": bool(parm.keyframes()) or parm.isLocked(),
            })
        parms.append({
            "name": pt.name(),
            "label": template.label() or pt.name(),
            "type": kind,
            "folders": list(pt.containingFolders()),
            "hidden": pt.isHidden(),
            "disabled": pt.isDisabled(),
            "menu": _parm_menu(pt[0], template) if kind in ("menu", "string", "int") else None,
            "components": components,
        })
    summary = _node_summary(node)
    summary["parms"] = parms
    return summary


def _set_parm(parm, kind, value):
    if kind == "toggle":
        parm.set(1 if value else 0)
    elif kind == "menu":
        parm.set(str(value))
    elif kind == "float":
        parm.set(float(value))
    elif kind == "int":
        parm.set(int(value))
    elif kind == "string":
        parm.set(str(value))
    else:
        raise HipError(f"この種類のパラメータは変更できません: {kind}")


def set_parms(path, values):
    """values は {parm tuple 名: [値, ...]}。変更できなかったものは errors に入れて返す"""
    global _unsaved
    node = _get_node(path)
    errors = []
    with hou.undos.group("houdini-headless: set parms"):
        for name, comps in values.items():
            pt = node.parmTuple(name)
            if pt is None:
                errors.append(f"{name}: パラメータがありません")
                continue
            kind = _parm_type_name(pt.parmTemplate())
            if not isinstance(comps, list):
                comps = [comps]
            for parm, value in zip(pt, comps):
                if value is None:
                    continue
                if parm.keyframes():
                    errors.append(f"{parm.name()}: エクスプレッションかアニメーションが付いているので変更できません")
                    continue
                if parm.isLocked():
                    errors.append(f"{parm.name()}: ロックされているので変更できません")
                    continue
                try:
                    _set_parm(parm, kind, value)
                    _unsaved = True
                except (ValueError, TypeError, hou.Error, HipError) as e:
                    errors.append(f"{parm.name()}: {e}")
    result = node_parms(path)
    result["setErrors"] = errors
    result["status"] = status()
    return result


# --- ROP の実行 --------------------------------------------------------------

def _output_files(node):
    outputs = []
    for name in OUTPUT_PARMS:
        parm = node.parm(name)
        if parm is None:
            continue
        try:
            value = parm.evalAsString()
        except hou.Error:
            continue
        if value:
            outputs.append({"parm": name, "path": value, "exists": os.path.exists(value)})
    return outputs


def render(path):
    node = _get_node(path)
    if not isinstance(node, hou.RopNode):
        raise HipError(f"ROP ノードではありません: {path}")

    started = time.time()
    failure = None
    try:
        node.render(verbose=False)
    except hou.OperationFailed as e:
        failure = e.instanceMessage()
    elapsed = time.time() - started

    return {
        "path": node.path(),
        "ok": failure is None and not node.errors(),
        "elapsed": round(elapsed, 2),
        "failure": failure,
        "errors": list(node.errors()),
        "warnings": list(node.warnings()),
        "outputs": _output_files(node),
        "status": status(),
    }
