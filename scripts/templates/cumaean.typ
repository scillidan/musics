#let cumaean-cover(
  title: none,
  artist: none,
  license: none,
  license-url: none,
  wave: none,
  page-size: "a4",
  flipped: true,
  image-width: 129.5mm,
  wave-aspect: 1.375,
  base-size: 11pt,
  line-size: 0.9em,
  text-font: "Sarasa Mono SC",
  block-gap: 0.5em,
  page-margin-y: 20mm,
  frame-stroke: 0.4pt,
  frame-color: rgb(50%, 50%, 50%),
  frame-pad-y: 4mm,
  frame-pad-x: 8mm,
) = {
  set page(
    page-size,
    flipped: flipped,
    margin: (top: page-margin-y, bottom: page-margin-y),
  )
  set text(size: base-size, font: text-font)

  if wave == none or wave == "" {
    return
  }

  let has-artist = artist != none and artist != ""
  let has-license = license != none and license != ""
  let has-license-url = license-url != none and license-url != ""

  let parts = ()
  if title != none and title != "" {
    parts.push([#title])
  }
  if has-artist {
    parts.push([by])
    parts.push([#artist])
  }
  if has-license {
    parts.push(text("/"))
    if has-license-url {
      parts.push(link(license-url)[#license])
    } else {
      parts.push([#license])
    }
  }

  set align(center + horizon)
  block(width: image-width)[
    #set align(left)
    #if parts.len() > 0 {
      text(size: line-size)[#parts.join([ ])]
      v(block-gap)
    }
    #block(
      width: 100%,
      above: 0pt,
      below: 0pt,
      stroke: frame-stroke + frame-color,
      inset: (x: frame-pad-x, y: frame-pad-y),
    )[
      #let inner-w = image-width - frame-pad-x * 2 - frame-stroke * 2
      #image(wave, width: 100%, height: inner-w * wave-aspect, fit: "contain")
    ]
  ]
}
