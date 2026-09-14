// Instrumental cover-only poster template.
// Layout: a single full-page image grid (cover only, or cover + artist).

#import "/scripts/templates/base.typ": image-box, default-font

#let instrumental-poster(
  name: "",
  images: (),
  columns: 1,
  rows: none,
  page-size: "a5",
  flipped: true,
  margin: 5%,
  font: default-font,
  title-size: 2em,
  show-title: false,
  image-gutter: 0.5em,
) = {
  set page(page-size, flipped: flipped, margin: margin)
  set text(font: font)

  let n = images.len()
  if n == 0 {
    return
  }

  let c = if rows != none {
    calc.ceil(n / rows)
  } else {
    columns
  }
  let r = if rows != none {
    rows
  } else {
    calc.ceil(n / c)
  }

  grid(
    columns: (1fr,) * c,
    rows: (1fr,) * r,
    gutter: image-gutter,
    ..images.map(image-box),
  )

  if show-title {
    place(
      bottom + center,
      dy: -1em,
      text(size: title-size, weight: "bold", fill: white, stroke: 0.5pt + black)[#name],
    )
  }
}
