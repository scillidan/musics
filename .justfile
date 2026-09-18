# weekly
weekly-typ name:
	cd weekly && uv run ../scripts/gen_weekly.py typ "{{name}}"
weekly-add name:
	cd weekly && uv run ../scripts/gen_weekly.py add "{{name}}"

# instrumental
instrumental-typ name:
	cd instrumental && uv run ../scripts/gen_instrumental.py typ "{{name}}"
instrumental-add name:
	cd instrumental && uv run ../scripts/gen_instrumental.py add "{{name}}"

# cd
cd-typ name:
	cd cd && uv run ../scripts/gen_album.py typ "{{name}}"
cd-add name:
	cd cd && uv run ../scripts/gen_album.py add "{{name}}"

# ost
ost-typ name:
	cd ost && uv run ../scripts/gen_album.py typ "{{name}}"
ost-add name:
	cd ost && uv run ../scripts/gen_album.py add "{{name}}"

# mid
mid-typ name:
	cd mid && uv run ../scripts/gen_mid.py typ "{{name}}"
mid-add name:
	cd mid && uv run ../scripts/gen_mid.py add "{{name}}"