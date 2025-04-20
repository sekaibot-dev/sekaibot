CHARACTER = [{
	'type': '搞怪',
	'characters': [{
		'character_id': 'lucy-voice-laibixiaoxin',
		'character_name': '小新',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-laibixiaoxin.wav'
	}, {
		'character_id': 'lucy-voice-houge',
		'character_name': '猴哥',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-houge.wav'
	}, {
		'character_id': 'lucy-voice-guangdong-f1',
		'character_name': '东北老妹儿',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-guangdong-f1.wav'
	}, {
		'character_id': 'lucy-voice-guangxi-m1',
		'character_name': '广西大表哥',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-guangxi-m1.wav'
	}, {
		'character_id': 'lucy-voice-m8',
		'character_name': '说书先生',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-m8.wav'
	}, {
		'character_id': 'lucy-voice-male1',
		'character_name': '憨憨小弟',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-male1.wav'
	}, {
		'character_id': 'lucy-voice-male3',
		'character_name': '憨厚老哥',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-male3.wav'
	}]
}, {
	'type': '古风',
	'characters': [{
		'character_id': 'lucy-voice-daji',
		'character_name': '妲己',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-daji.wav'
	}, {
		'character_id': 'lucy-voice-silang',
		'character_name': '四郎',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-silang.wav'
	}, {
		'character_id': 'lucy-voice-lvbu',
		'character_name': '吕布',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-lvbu.wav'
	}]
}, {
	'type': '现代',
	'characters': [{
		'character_id': 'lucy-voice-lizeyan',
		'character_name': '霸道总裁',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-lizeyan-2.wav'
	}, {
		'character_id': 'lucy-voice-suxinjiejie',
		'character_name': '酥心御姐',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-suxinjiejie.wav'
	}, {
		'character_id': 'lucy-voice-xueling',
		'character_name': '元气少女',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-xueling.wav'
	}, {
		'character_id': 'lucy-voice-f37',
		'character_name': '文艺少女',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-f37.wav'
	}, {
		'character_id': 'lucy-voice-male2',
		'character_name': '磁性大叔',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-male2.wav'
	}, {
		'character_id': 'lucy-voice-female1',
		'character_name': '邻家小妹',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-female1.wav'
	}, {
		'character_id': 'lucy-voice-m14',
		'character_name': '低沉男声',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-m14.wav'
	}, {
		'character_id': 'lucy-voice-f38',
		'character_name': '傲娇少女',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-f38.wav'
	}, {
		'character_id': 'lucy-voice-m101',
		'character_name': '爹系男友',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-m101.wav'
	}, {
		'character_id': 'lucy-voice-female2',
		'character_name': '暖心姐姐',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-female2.wav'
	}, {
		'character_id': 'lucy-voice-f36',
		'character_name': '温柔妹妹',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-f36.wav'
	}, {
		'character_id': 'lucy-voice-f34',
		'character_name': '书香少女',
		'preview_url': 'https://res.qpt.qq.com/qpilot/tts_sample/group/lucy-voice-f34.wav'
	}]
}]

def get_character_name_list_text() -> str:
    """返回分组+人名的展示文本，供用户选择。"""
    lines = []
    for group in CHARACTER:
        lines.append(f"【{group['type']}】")
        for char in group["characters"]:
            lines.append(f" - {char['character_name']}")
        lines.append("")  # 空行分组
    return "\n".join(lines)

def get_character_id_by_name(group_type: str, name: str) -> str | None:
    """通过分组和角色名字获取对应的 character_id"""
    for group in CHARACTER:
        if group["type"] == group_type:
            for char in group["characters"]:
                if char["character_name"] == name:
                    return char["character_id"]
    return None

def parse_character_command(text: str) -> str | None:
    """
    解析 /角色 分组名 角色名 指令，返回 character_id 或 None。
    """

    parts = text.strip().split()
    if len(parts) < 2 or not parts[0].startswith("/角色"):
        return None

    group = parts[1]
    name = "".join(parts[2:])  # 支持多词角色名

    return get_character_id_by_name(group, name)