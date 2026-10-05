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

# song (renamed from cd) - weekly-style covers; album add switches per-track posters
song-typ name:
	cd song && uv run ../scripts/gen_album.py typ "{{name}}"
song-add name:
	cd song && uv run ../scripts/gen_album.py add "{{name}}"

# ost
ost-chp name:
	cd ost && uv run ../scripts/gen_album.py chp "{{name}}"
ost-typ name:
	cd ost && uv run ../scripts/gen_album.py typ "{{name}}"
ost-add name:
	cd ost && uv run ../scripts/gen_album.py add "{{name}}"

# mid - sheet-music cover videos from MIDI
# mid-typ: generate cover only (typ/pdf/jpg), no audio
mid-typ name:
	cd mid && uv run ../scripts/gen_mid.py typ "{{name}}"
# mid-add: generate mp4; reuse _output/typs/*.typ if present, else create from scratch
mid-add name:
	cd mid && uv run ../scripts/gen_mid.py add "{{name}}"

# cumaean - waveform-stack cover videos from source audio (CUMAEAN_SOURCE)
cumaean-typ name:
	cd cumaean && uv run ../scripts/gen_cumaean.py typ "{{name}}"
cumaean-add name:
	cd cumaean && uv run ../scripts/gen_cumaean.py add "{{name}}"

# song - lrc/metadata preprocessing (strip credits into metadata/, normalize lrc)
song-prep *args:
	cd song && uv run ../scripts/prep_lrc_meta.py {{args}}