// CV layout. Data comes from jobscout/cv_render.py (data.json + optional photo.jpg);
// every text value is a plain string, so CV content can never be read as Typst markup.
#let d = json("data.json")
// Fit preset from cv_render: body size and a vertical-spacing factor, tightened only to avoid a near-empty page 2.
#let fs = d.fit.size * 1pt
#let g = d.fit.gap

#let navy = rgb("#1F3864")
#let blue = rgb("#2E74B5")
#let slate = rgb("#44546A")
#let muted = rgb("#5F6368")
#let hair = rgb("#DDE1E6")
#let ink = rgb("#262626")

#set document(title: d.name, author: d.name)
#set page(paper: "a4", margin: (x: 18mm, top: 16mm, bottom: 15mm))
// Justified like the template; hyphenation only where it saves a visibly stretched line.
#set text(font: "Inter", size: fs, fill: ink, lang: d.lang, costs: (hyphenation: 300%))
#set par(justify: true, leading: 0.6em, spacing: 0.75em * g)
#set list(indent: 2mm, body-indent: 1.6mm, spacing: 0.75em * g, marker: text(fill: ink)[•])

#let inline(segs, bold-fill: ink) = {
  for s in segs {
    let c = text(s.t)
    if s.i { c = emph(c) }
    if s.b { c = text(weight: "bold", fill: bold-fill, c) }
    if s.u != none { c = link(s.u, c) }
    c
  }
}

#let contact-item(c) = box({
  if c.label != none { text(weight: "bold", fill: slate, c.label + ":") + h(3pt) }
  if c.url != none { link(c.url, c.text) } else { c.text }
})

#let header = {
  set par(justify: false)
  set text(hyphenate: false)
  text(size: 22pt, weight: "bold", fill: navy, upper(d.name))
  if d.headline.len() > 0 {
    block(above: 7pt, text(size: 11.5pt, weight: "bold", fill: slate, inline(d.headline, bold-fill: slate)))
  }
  if d.contact.len() > 0 {
    block(above: 9pt, text(size: 8.5pt, fill: muted, d.contact.map(contact-item).join(h(12pt))))
  }
}

#grid(
  columns: if d.has_photo { (1fr, 25mm) } else { (1fr,) },
  column-gutter: 8mm,
  align: (horizon, top),
  header,
  ..if d.has_photo { (box(clip: true, radius: 2pt, image("photo.jpg", width: 25mm, height: 31mm, fit: "cover")),) },
)
#block(above: 9pt * g, below: 0pt, line(length: 100%, stroke: 1.1pt + blue))

#for p in d.intro {
  block(above: 10pt, inline(p))
}

#let section-title(title) = block(sticky: true, above: 15pt * g, below: 8pt * g, {
  text(size: 12pt, weight: "bold", fill: navy, upper(title))
  block(above: 5pt, below: 0pt, line(length: 100%, stroke: 0.6pt + hair))
})

#let entry(e) = {
  block(sticky: true, above: 10pt * g, below: 6pt * g, {
    set par(justify: false)
    set text(hyphenate: false)
    grid(
      columns: (1fr, auto),
      column-gutter: 6mm,
      align: (left + top, right + top),
      text(size: 10pt, weight: "bold", fill: blue, e.title),
      if e.meta != "" { move(dy: 0.8pt, text(size: 8.5pt, fill: muted, e.meta)) },
    )
  })
  if e.bullets.len() > 0 { list(..e.bullets.map(b => inline(b))) }
  for p in e.paras { block(above: 5pt * g, inline(p)) }
}

#let para(p) = {
  // "**Label:** values" lines (skills, languages) read better ragged, like the template.
  let labelled = p.len() > 0 and p.first().b
  block(above: 6pt * g, {
    set par(justify: not labelled)
    inline(p, bold-fill: navy)
  })
}

#for s in d.sections {
  section-title(s.title)
  for b in s.blocks {
    if b.kind == "entry" { entry(b) }
    else if b.kind == "list" { block(above: 6pt * g, list(..b.items.map(i => inline(i)))) }
    else { para(b.segs) }
  }
}
