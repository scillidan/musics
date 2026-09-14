// Weekly lyric poster template.
// Layout: left image column (cover + optional artist photos),
//         right lyrics column with configurable columns/splits.

#import "/scripts/templates/base.typ": image-box, split-chunks, default-font

#let lyric-poster(
  name: "",
  cover: none,
  artists: (),
  lrc: none,
  left-ratio: 0.35,
  lyrics-columns: 1,
  lyrics-column-widths: none,
  lyrics-columns-split: none,
  lyrics-size: 0.55em,
  lyrics-wrap-leading: none,
  lyrics-spacing: 5pt,
  lyrics-paragraph-spacing: 1em,
  lyrics-inset: (top: 0pt, left: 0pt),
  image-inset: (top: 0pt, left: 0pt),
  spacing_all: 10pt,
  title-size: 1em,
  lyrics-hanging-indent: 1.33em,
  artist-grid-cols: none,
  artist-grid-rows: none,
  artist-gutter: 5pt,
  page-size: "a5",
  flipped: true,
  font: default-font,
) = {
  // Strip LRC timestamps.
  let lyrics-raw = if lrc != none and lrc != "" {
    read(lrc)
      .split("\n")
      .map(line => line.replace(regex("^\\[(.+?)]"), "").trim())
      .join("\n")
  } else {
    ""
  }
  let lyrics-lines = lyrics-raw.split("\n")

  let has-cover = cover != none and cover != ""
  let has-artists = artists.len() > 0
  let has-images = has-cover or has-artists

  set page(page-size, flipped: flipped, margin: spacing_all)
  set text(font: font)

  let title-block = {
    text(size: title-size, weight: "bold")[#name]
    v(spacing_all - 0.5em)
  }

  let render-lyrics(lines) = {
    set text(size: lyrics-size)
  let par-args = (
    justify: false,
    hanging-indent: lyrics-hanging-indent,
    spacing: lyrics-spacing,
  )
    if lyrics-wrap-leading != none {
      par-args = par-args + (leading: lyrics-wrap-leading)
    }
    set par(..par-args)

    for line in lines {
      if line.trim() == "" {
        v(lyrics-paragraph-spacing)
      } else {
        line
        parbreak()
      }
    }
  }

  // Artist photo grid.
  let artist-area = if has-artists {
    let n = artists.len()
    let c = if artist-grid-cols != none {
      artist-grid-cols
    } else if artist-grid-rows != none {
      calc.ceil(n / artist-grid-rows)
    } else if n <= 3 {
      n
    } else {
      calc.ceil(calc.sqrt(n))
    }
    grid(
      columns: (1fr,) * c,
      rows: (1fr,) * calc.ceil(n / c),
      gutter: artist-gutter,
      ..artists.map(image-box),
    )
  } else {
    []
  }

  let lyrics-area = [
    #block(
      width: 100%,
      height: 100%,
      inset: lyrics-inset,
      {
        let use-custom-widths = lyrics-column-widths != none and lyrics-column-widths.len() > 0
        let use-splits = lyrics-columns-split != none and lyrics-columns-split.len() > 0

        let widths = if use-custom-widths {
          lyrics-column-widths
        } else {
          (1fr,) * lyrics-columns
        }
        let n = widths.len()
        let split-points = if use-splits {
          lyrics-columns-split
        } else {
          let chunk = calc.ceil(lyrics-lines.len() / n)
          range(n - 1).map(i => calc.min((i + 1) * chunk, lyrics-lines.len()))
        }
        let bounds = (0,) + split-points + (lyrics-lines.len(),)

      grid(
        columns: widths,
        rows: (auto, 1fr),
        gutter: spacing_all,
        grid.cell(colspan: n, title-block),
        ..range(n).map(i => render-lyrics(lyrics-lines.slice(bounds.at(i), bounds.at(i + 1)))),
      )
      },
    )
  ]

  if has-images {
    grid(
      columns: (left-ratio * 1fr, (1 - left-ratio) * 1fr),
      gutter: spacing_all,
      [
        #block(
          width: 100%,
          height: 100%,
          inset: image-inset,
          {
            if has-cover and has-artists {
              grid(
                columns: 1,
                rows: (1fr, 1fr),
                gutter: artist-gutter,
                image-box(cover),
                artist-area,
              )
            } else if has-cover {
              image-box(cover)
            } else {
              artist-area
            }
          },
        )
      ],
      lyrics-area,
    )
  } else {
    lyrics-area
  }
}
