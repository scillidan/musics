#import "/scripts/templates/base.typ": image-box, text-block, split-chunks, default-font

#let parse-chapters(path) = {
  read(path).split("\n").filter(l => l.len() > 9).map(l => l.slice(9))
}

#let album-poster(
  title: "",
  artist: "",
  year: "",
  images: (),
  chapters: (),
  chapters-path: none,
  columns: auto,
  column-gutter: 0.5em,
  page-size: "a5",
  flipped: true,
  margin: 5%,
  font: default-font,
  base-size: 8pt,
  title-size: 2.5em,
  subtitle-size: 1.5em,
  body-size: 1.1em,
  image-text-gutter: 1em,
  inset: (x: 1em, y: 1em),
) = {
  set page(page-size, flipped: flipped, margin: margin)
  set text(font: font, size: base-size)

  let chapter-list = if chapters-path != none {
    parse-chapters(chapters-path)
  } else {
    chapters
  }

  let has-images = images.len() > 0

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

  let image-area = if images.len() == 1 {
    image-box(images.at(0))
  } else if images.len() > 1 {
    grid(
      columns: 1,
      rows: (1fr,) * images.len(),
      gutter: 0.5em,
      ..images.map(image-box),
    )
  } else {
    []
  }

  let text-area = text-block({
    text(size: title-size, weight: "bold")[#title]
    linebreak()
    v(0.2em)

    if artist != "" or year != "" {
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
      linebreak()
    }

    v(1em)

    if n-cols <= 1 {
      text(size: body-size)[
        #chapter-list.join("\n")
      ]
    } else {
      let chunks = split-chunks(chapter-list, n-cols)
      grid(
        columns: (1fr,) * n-cols,
        gutter: column-gutter,
        ..chunks.map(chunk => [
          #text(size: body-size)[#chunk.join("\n")]
        ]),
      )
    }
  }, inset: inset)

  if has-images {
    grid(
      columns: 2,
      gutter: image-text-gutter,
      image-area,
      text-area,
    )
  } else {
    text-area
  }
}
