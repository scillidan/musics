// MIDI sheet-music cover template.
// Layout: two A5 portrait score pages side by side, filling the A4 landscape
// cover.  The title floats in the top white space and page numbers float in
// the bottom white space of each page, using the score's built-in margins.

#let mid-cover(
  title: none,
  pages: (),
  page-size: "a4",
  flipped: true,
  page-width: 148mm,
  page-height: 210mm,
  gutter: 1mm,
  title-size: 16pt,
  page-number-size: 10pt,
  title-offset: 8mm,
  page-number-offset: 8mm,
) = {
  set page(page-size, flipped: flipped, margin: 0pt)

  let count = pages.len()
  if count == 0 {
    return
  }

  let visible-pages = pages.slice(0, calc.min(count, 2))

  // Background: two A5 pages filling the A4 landscape page.
  place(center + horizon)[
    #grid(
      columns: (page-width,) * visible-pages.len(),
      rows: (page-height,),
      gutter: gutter,
      ..visible-pages.map(p => image(p, width: page-width, height: page-height, fit: "contain")),
    )
  ]

  // Title centered across the top of the cover.
  if title != none and title != "" {
    place(top + center, dy: title-offset)[
      #text(size: title-size, weight: "bold")[#title]
    ]
  }

  // Page numbers centered at the bottom of each score page.
  for i in range(visible-pages.len()) {
    let dx = (i - 0.5) * (page-width + gutter)
    place(bottom + center, dx: dx, dy: -page-number-offset)[
      #text(size: page-number-size)[#(i + 1)]
    ]
  }
}
