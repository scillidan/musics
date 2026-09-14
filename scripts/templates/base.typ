// Reusable layout building blocks for music poster templates.
// Importing this module does NOT apply any global set/show rules;
// each template function must set up its own page/text rules internally.

#let default-font = ("MonaspiceNe NFM", "Sarasa Mono SC")

// Render a single image so it fills its cell without overflowing.
// Returns an empty box if path is none/empty so callers don't need guards.
#let image-box(
  path,
  stroke-width: 0.15pt,
  stroke-color: black,
) = {
  if path == none or path == "" {
    return []
  }
  box(
    width: 100%,
    height: 100%,
    stroke: stroke-width + stroke-color,
    image(path, width: 100%, height: 100%, fit: "contain"),
  )
}

// Wrap content in a full-size block with uniform inset.
#let text-block(
  content,
  inset: (x: 1em, y: 1em),
) = block(
  width: 100%,
  height: 100%,
  inset: inset,
  content,
)

// Split a flat array into roughly equal chunks for multi-column layout.
// Returns an array of arrays; the last chunk may be shorter.
#let split-chunks(items, n) = {
  if n <= 1 {
    return (items,)
  }
  let len = items.len()
  let chunk = calc.ceil(len / n)
  let result = ()
  let i = 0
  while i < len {
    result.push(items.slice(i, calc.min(i + chunk, len)))
    i += chunk
  }
  result
}
