// Cover letter layout. Data comes from jobscout/cv_render.py (data.json); every text value
// is a plain string, so letter content can never be read as Typst markup.
#let d = json("data.json")

#set document(title: d.title, author: d.author)
#set page(paper: "a4", margin: 25mm)
#set text(font: "Inter", size: 11pt, fill: rgb("#262626"), lang: d.lang)
#set par(leading: 0.75em, spacing: 1.2em)

// A paragraph is a list of lines; single line breaks inside it (greeting, sign-off) are kept.
#for para in d.paragraphs {
  par(para.join(linebreak()))
}
