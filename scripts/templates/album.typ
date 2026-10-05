// Album/song poster template, weekly-style layout.
// Left column: cover + optional artist photos (weekly lookup semantics,
// see lib/common.py find_cover/find_artist_images).
// Right column: title block, then either lyrics (lrc) or the album
// tracklist (chapters). Singles and per-track posters pass lrc; the album
// overview poster passes chapters.

#import "/scripts/templates/base.typ": image-box, text-block, split-chunks, default-font

#let parse-chapters(path) = {
  read(path).split("\n").filter(l => l.len() > 9).map(l => l.slice(9))
}

#let strip-lrc(path) = {
  read(path)
    .split("\n")
    .map(line => line.replace(regex("^\\[(.+?)]"), "").trim())
    .join("\n")
}

#let album-poster(
  title: "",
  artist: "",
  year: "",
  images: (),
  cover: none,
  artists: (),
  chapters: (),
  chapters-path: none,
  lrc: none,
  columns: auto,
  column-gutter: 0.5em,
  left-ratio: 0.35,
  spacing-all: 10pt,
  page-size: "a5",
  flipped: true,
  font: default-font,
  base-size: 8pt,
  title-size: 2em,
  subtitle-size: 1.2em,
  body-size: 0.9em,
  lyrics-columns: 1,
  lyrics-size: 0.65em,
  lyrics-spacing: 5pt,
  lyrics-paragraph-spacing: 1em,
  lyrics-hanging-indent: 1.33em,
  image-gutter: 5pt,
) = {
  set page(page-size, flipped: flipped, margin: spacing-all)
  set text(font: font, size: base-size)

  let chapter-list = if chapters-path != none {
    parse-chapters(chapters-path)
  } else {
    chapters
  }
  let has-lrc = lrc != none and lrc != ""
  let has-cover = cover != none and cover != ""
  let has-artists = artists.len() > 0
  let has-images = images.len() > 0 or has-cover or has-artists

  // Artist photo grid (same semantics as weekly.typ).
  let artist-area = if has-artists {
    let n = artists.len()
    let c = if n <= 3 {
      n
    } else {
      calc.ceil(calc.sqrt(n))
    }
    grid(
      columns: (1fr,) * c,
      rows: (1fr,) * calc.ceil(n / c),
      gutter: image-gutter,
      ..artists.map(image-box),
    )
  } else {
    []
  }

  let image-area = if images.len() == 1 {
    image-box(images.at(0))
  } else if images.len() > 1 {
    grid(
      columns: 1,
      rows: (1fr,) * images.len(),
      gutter: image-gutter,
      ..images.map(image-box),
    )
  } else if has-cover and has-artists {
    grid(
      columns: 1,
      rows: (1fr, 1fr),
      gutter: image-gutter,
      image-box(cover),
      artist-area,
    )
  } else if has-cover {
    image-box(cover)
  } else if has-artists {
    artist-area
  } else {
    []
  }

  let title-block = {
    text(size: title-size, weight: "bold")[#title]
    if artist != "" or year != "" {
      linebreak()
      v(0.2em)
      let subtitle-parts = ()
      if artist != "" {
        subtitle-parts.push(artist)
      }
      if year != "" {
        subtitle-parts.push(year)
      }
      text(size: subtitle-size, weight: "medium", style: "italic")[
        #subtitle-parts.join(", ")
      ]
    }
    v(spacing-all)
  }

  let lyrics-lines = if has-lrc {
    strip-lrc(lrc).split("\n")
  } else {
    ()
  }

  let render-lyrics(lines) = {
    set text(size: lyrics-size)
    set par(
      justify: false,
      hanging-indent: lyrics-hanging-indent,
      spacing: lyrics-spacing,
    )
    for line in lines {
      if line.trim() == "" {
        v(lyrics-paragraph-spacing)
      } else {
        line
        parbreak()
      }
    }
  }

  // Tracklist columns (album overview mode).
  let n-cols = if columns == auto {
    let len = chapter-list.len()
    if len > 40 {
      3
    } else if len > 20 {
      2
    } else {
      1
    }
  } else {
    columns
  }

  let body-area = if has-lrc {
    let n = lyrics-columns
    let chunk = calc.ceil(lyrics-lines.len() / n)
    let split-points = range(n - 1).map(i => calc.min((i + 1) * chunk, lyrics-lines.len()))
    let bounds = (0,) + split-points + (lyrics-lines.len(),)
    grid(
      columns: (1fr,) * n,
      rows: (auto, 1fr),
      gutter: spacing-all,
      grid.cell(colspan: n, title-block),
      ..range(n).map(i => render-lyrics(lyrics-lines.slice(bounds.at(i), bounds.at(i + 1)))),
    )
  } else if n-cols <= 1 {
    title-block
    text(size: body-size)[
      #chapter-list.join("\n")
    ]
  } else {
    let chunks = split-chunks(chapter-list, n-cols)
    grid(
      columns: (1fr,) * n-cols,
      rows: (auto, 1fr),
      gutter: column-gutter,
      grid.cell(colspan: n-cols, title-block),
      ..chunks.map(chunk => [
        #text(size: body-size)[#chunk.join("\n")]
      ]),
    )
  }

  let text-area = text-block(body-area)

  if has-images {
    grid(
      columns: (left-ratio * 1fr, (1 - left-ratio) * 1fr),
      gutter: spacing-all,
      image-area,
      text-area,
    )
  } else {
    text-area
  }
}
