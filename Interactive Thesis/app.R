
# ---- 1. Libraries and existing Sankey ----

pacman::p_load(shiny, networkD3, htmlwidgets)

options(traceability.in_shiny = TRUE)
source("sankey.R", local = TRUE)
options(traceability.in_shiny = FALSE)


# ---- 2. Read the existing project CSVs once ----

sections <- read.csv(
  "thesis_sections.csv",
  stringsAsFactors = FALSE,
  encoding = "UTF-8"
)

references <- read.csv(
  "thesis_references.csv",
  stringsAsFactors = FALSE,
  fileEncoding = "UTF-8-BOM"
)

# `links` comes from sankey.R.
# Original thesis content comes from the CSVs.


section_row <- function(code) {
  
  index <- match(code, sections$code)
  
  if (is.na(index)) return(NULL)
  
  sections[index, , drop = FALSE]
}


section_title <- function(code) {
  
  item <- section_row(code)
  
  if (is.null(item)) return(code)
  
  paste(code, item$display_title[[1]])
}


# Exclude figures, tables, and captions as agreed.

section_body <- function(code) {
  
  item <- section_row(code)
  
  if (is.null(item)) return("")
  
  html <- item$body_html[[1]]
  
  if (is.na(html) || !nzchar(html)) return("")
  
  html <- gsub(
    '(?s)<figure\\b[^>]*>.*?</figure>',
    "",
    html,
    perl = TRUE
  )
  
  html <- gsub(
    '(?s)<table\\b[^>]*>.*?</table>',
    "",
    html,
    perl = TRUE
  )
  
  html <- gsub(
    '(?s)<p class="thesis-caption"[^>]*>.*?</p>',
    "",
    html,
    perl = TRUE
  )
  
  html
}


# Retrieve section codes for each connection.
# F1-F7 anchors take precedence over the generic 4.2.1 code.

connection_codes <- function(mapping) {
  
  source_codes <- unlist(
    mapping[c("SourceSectionCode1", "SourceSectionCode2")],
    use.names = FALSE
  )
  
  source_codes <- unique(
    source_codes[
      !is.na(source_codes) & nzchar(source_codes)
    ]
  )
  
  target_code <- mapping$TargetAnchor[[1]]
  
  if (is.na(target_code) || !nzchar(target_code)) {
    target_code <- mapping$TargetSectionCode[[1]]
  }
  
  list(
    source = source_codes,
    target = target_code
  )
}


sort_section_codes <- function(codes) {
  
  codes <- unique(
    codes[!is.na(codes) & nzchar(codes)]
  )
  
  codes <- codes[codes %in% sections$code]
  
  codes[
    order(
      sections$sort_order[
        match(codes, sections$code)
      ]
    )
  ]
}


node_connections <- function(id) {
  
  links[
    links$Source == id | links$Target == id,
    ,
    drop = FALSE
  ]
}


node_section_codes <- function(id, own_only = FALSE) {
  
  rows <- node_connections(id)
  
  if (!nrow(rows)) {
    return(
      if (id == "PR6") "1.3.3" else character(0)
    )
  }
  
  codes <- character(0)
  
  for (i in seq_len(nrow(rows))) {
    
    row <- rows[i, , drop = FALSE]
    parts <- connection_codes(row)
    
    if (!own_only || row$Source[[1]] == id) {
      codes <- c(codes, parts$source)
    }
    
    if (!own_only || row$Target[[1]] == id) {
      codes <- c(codes, parts$target)
    }
  }
  
  sort_section_codes(codes)
}


# Citations in body_html already link to the original sources.
# Reference IDs connect those citations to the bibliography CSV.

section_reference_ids <- function(codes) {
  
  ids <- character(0)
  
  for (code in codes) {
    
    html <- section_body(code)
    
    matches <- regmatches(
      html,
      gregexpr(
        'data-reference-id="[^"]+"',
        html,
        perl = TRUE
      )
    )[[1]]
    
    ids <- c(
      ids,
      sub(
        '^data-reference-id="([^"]+)"$',
        '\\1',
        matches
      )
    )
  }
  
  unique(ids)
}


reference_list <- function(codes) {
  
  ids <- section_reference_ids(codes)
  
  cited <- references[
    match(ids, references$reference_id),
    ,
    drop = FALSE
  ]
  
  cited <- cited[
    !is.na(cited$reference_id),
    ,
    drop = FALSE
  ]
  
  if (!nrow(cited)) return(NULL)
  
  tagList(
    
    h3("References cited in these sections"),
    
    tags$ul(
      lapply(seq_len(nrow(cited)), function(i) {
        
        entry <- cited$entry[[i]]
        url <- cited$url[[i]]
        
        tags$li(
          if (!is.na(url) && nzchar(url)) {
            
            tags$a(
              href = url,
              target = "_blank",
              rel = "noopener noreferrer",
              entry
            )
            
          } else {
            
            entry
          }
        )
      })
    )
  )
}


# ---- 3. Existing short node labels ----
# These are retained because they are not separately
# represented in the thesis sections CSV.

node_labels <- c(
  
  PR1 = "Practitioner-related factors",
  PR2 = "Patient-related factors",
  PR3 = "Tasks",
  PR4 = "Tools & Technologies",
  PR5 = "Organization",
  PR6 = "External Environment",
  
  R1 = "Structured reasoning",
  R2 = "Evidence provision",
  R3 = "Integration of relevant patient data",
  R4 = "Decision consistency",
  R5 = "Reasoning transparency",
  R6 = "Patient-data quality and availability",
  R7 = "Workflow compatibility",
  R8 = "Low interaction burden",
  R9 = "Preserve professional judgement",
  R10 = "Relevant information for informed decisions",
  R11 = "Understandable patient information",
  R12 = "Low-barrier use of patient-facing support",
  R13 = "Patient autonomy in treatment decisions",
  R14 = "Preservation of clinician-patient communication",
  
  SDM1 = paste(
    "Shared clinician-patient deliberation integrating",
    "clinical knowledge and patient preferences"
  ),
  
  SDM2 = paste(
    "Non-directive support with human control",
    "of the final decision"
  ),
  
  P1 = "Shared interface for clinician-patient participation",
  P2 = "Visible, predictable, low-burden interaction",
  P3 = "Predictable, decision-relevant visual organization",
  P4 = "Neutral, even-handed option presentation",
  P5 = "Flexible comparison and revision of options",
  
  P6 = paste(
    "Patient-understandable information",
    "with professional efficiency"
  ),
  
  P7 = "Evidence-grounded, traceable, maintainable knowledge",
  
  P8 = paste(
    "Practitioner-accessible reasoning",
    "and evidence verification"
  ),
  
  P9 = "Patient-relevant explanations of treatment trade-offs",
  P10 = "Timely decision support with minimal interruption",
  P11 = "Reuse of existing clinical data",
  P12 = "Syntactic and semantic interoperability",
  P13 = "Flexible revision as information changes",
  P14 = "Error prevention and reversible actions",
  
  # Feature names now come directly from the thesis CSV.
  
  F1 = section_row("F1")$display_title[[1]],
  F2 = section_row("F2")$display_title[[1]],
  F3 = section_row("F3")$display_title[[1]],
  F4 = section_row("F4")$display_title[[1]],
  F5 = section_row("F5")$display_title[[1]],
  F6 = section_row("F6")$display_title[[1]],
  F7 = section_row("F7")$display_title[[1]]
)


# ---- 4. Original PR factor lists ----
# Retained from the existing app.R because the CSV
# does not contain equivalent structured lists.

problem_factors <- list(
  
  PR1 = c(
    "Experience, training, and specialization",
    "Heuristics, cognitive biases, and patient assumptions",
    "Procedure preferences"
  ),
  
  PR2 = c(
    "Clinical condition and history",
    "Aesthetic preferences, values, and priorities",
    "Financial circumstances",
    "Dental phobia"
  ),
  
  PR3 = c(
    "Choosing between multiple viable treatment options",
    "Balancing clinical findings and patient-specific factors",
    "Making long-term and potentially irreversible treatment decisions",
    "Integrating distributed clinical information",
    "Keeping up with and translating expanding evidence into practice"
  ),
  
  PR4 = c(
    "Fragmented medical and dental records",
    "Limited interoperability"
  ),
  
  PR5 = c(
    "Team-distributed data collection and recording",
    "Dependence on effective team communication",
    "Time constraints",
    "Practice profitability/business pressures"
  ),
  
  PR6 = "Insurance coverage"
)


# Feature descriptions are now derived from the
# original text of F1-F7 in thesis_sections.csv.

feature_sentences <- function(id) {
  
  item <- section_row(id)
  
  if (is.null(item)) return(character(0))
  
  paragraph <- strsplit(
    item$body_text[[1]],
    "\n\n",
    fixed = TRUE
  )[[1]][1]
  
  trimws(
    strsplit(
      paragraph,
      '(?<=\\.)\\s+(?=[A-Z])',
      perl = TRUE
    )[[1]]
  )
}


get_category <- function(id) {
  
  if (grepl("^PR", id)) return("Problem")
  
  if (grepl("^(R|SDM)", id)) {
    return("Solution requirement")
  }
  
  if (grepl("^P", id)) return("Design principle")
  
  if (grepl("^F", id)) return("Artefact feature")
  
  "Unknown"
}


all_ids <- names(node_labels)

node_categories <- stats::setNames(
  vapply(all_ids, get_category, character(1)),
  all_ids
)

solution_derived <- c(
  "R5", "R9", "R12", "R14", "SDM2"
)

# Preserve the original origin clarification.

origin_explanation <- paste(
  "This requirement was derived from the decision to use",
  "a Clinical Decision Support System (CDSS) as the",
  "proposed solution, rather than directly from the",
  "original problem groups."
)


# ---- 5. Thesis reader and clickable headings ----

js_arg <- function(x) {
  
  as.character(
    jsonlite::toJSON(x, auto_unbox = TRUE)
  )
}


section_button <- function(code) {
  
  item <- section_row(code)
  
  if (is.null(item)) return(NULL)
  
  tags$button(
    type = "button",
    class = "section-button",
    onclick = sprintf(
      "window.bookRead('section', %s)",
      js_arg(code)
    ),
    section_title(code)
  )
}


node_button <- function(id) {
  
  tags$button(
    type = "button",
    class = "node-title-button",
    onclick = sprintf(
      "window.bookRead('node', %s)",
      js_arg(id)
    ),
    paste0(id, ": ", node_labels[[id]])
  )
}


section_links <- function(codes, heading) {
  
  codes <- sort_section_codes(codes)
  
  if (!length(codes)) return(NULL)
  
  tagList(
    
    div(
      class = "section-role",
      heading
    ),
    
    lapply(codes, section_button)
  )
}


# Group sections by their original DSRM activity.

activity <- function(code) {
  
  if (grepl("^1\\.", code)) {
    return("Activity 1: Problem Identification and Motivation")
  }
  
  if (grepl("^2\\.", code)) {
    return("Activity 2: Definition of Solution Objectives")
  }
  
  if (grepl("^3\\.", code)) {
    return("Activity 3: Design and Development")
  }
  
  if (
    grepl("^4\\.", code) ||
    grepl("^F[0-9]+$", code)
  ) {
    return("Activity 4: Demonstration")
  }
  
  "Other thesis content"
}


section_role <- function(code) {
  
  if (grepl("^1\\.", code)) {
    return("Original problem statements")
  }
  
  if (grepl("^2\\.", code)) {
    return("Solution objectives and requirements")
  }
  
  if (grepl("^3\\.", code)) {
    return("Design principles")
  }
  
  if (grepl("^F[0-9]+$", code)) {
    return("Implemented artefact features")
  }
  
  "Demonstration and implementation context"
}


section_reader <- function(code) {
  
  item <- section_row(code)
  
  if (is.null(item)) return(NULL)
  
  html <- section_body(code)
  
  div(
    class = "reader-section",
    
    h4(section_title(code)),
    
    if (nzchar(html)) {
      
      HTML(html)
      
    } else {
      
      p("No text in this section of the current draft.")
    }
  )
}


# A section click opens one passage.
# A node-title click opens all unique associated passages,
# separated by DSRM activity and original role.

reader_content <- function(kind, id) {
  
  codes <- if (kind == "node") {
    node_section_codes(id)
  } else {
    id
  }
  
  codes <- sort_section_codes(codes)
  
  if (!length(codes)) {
    return(p("No associated sections."))
  }
  
  if (kind == "section") {
    
    return(
      tagList(
        section_reader(id),
        reference_list(codes)
      )
    )
  }
  
  activities <- vapply(
    codes,
    activity,
    character(1)
  )
  
  roles <- vapply(
    codes,
    section_role,
    character(1)
  )
  
  tagList(
    
    lapply(unique(activities), function(a) {
      
      activity_codes <- codes[activities == a]
      activity_roles <- roles[activities == a]
      
      div(
        class = "reader-activity",
        
        h3(a),
        
        lapply(unique(activity_roles), function(role) {
          
          tagList(
            
            h4(
              class = "reader-role",
              role
            ),
            
            lapply(
              activity_codes[activity_roles == role],
              section_reader
            )
          )
        })
      )
    }),
    
    reference_list(codes)
  )
}


mapping_sections <- function(mapping) {
  
  codes <- connection_codes(mapping)
  
  tagList(
    
    section_links(
      codes$source,
      "Source thesis sections"
    ),
    
    section_links(
      codes$target,
      "Target thesis section"
    )
  )
}


# ---- 6. Unified graph selection ----
# sankey.R already supplies d.connectionId.
# Node and link selection are both managed here.

shiny_sankey <- htmlwidgets::onRender(
  sankey,
  '
function(el, x, data) {

  var chart = this.sankey;
  var svg = d3.select(el).select("svg");
  var group = svg.select("g");

  var graphNodes = group.selectAll(
    "g.node, g.unmapped-node"
  );

  var paths = group.selectAll("path.link");
  var graphLinks = chart.links();

  var chosen = {
    kind: "",
    id: ""
  };

  var defaultWidth = 2.5;
  var defaultOpacity = 0.25;


  // ---- A. Replace previous hover handlers ----

  group.selectAll("g.node")
    .on("mouseover", null)
    .on("mouseout", null)
    .on("mouseover.traceability", null)
    .on("mouseout.traceability", null);

  paths
    .on("mouseover", null)
    .on("mouseout", null)
    .style("pointer-events", "none");


  // ---- B. Identify nodes ----

  function nodeId(d) {
    return d && d.name ? d.name : "PR6";
  }


  // ---- C. Preserve three-degree tracing ----

  function traceConnections(startNode) {

    var selectedLinks = new Set();

    function traverse(direction) {

      var visited = new Set([startNode]);
      var frontier = [startNode];

      for (var depth = 0; depth < 3; depth++) {

        if (!frontier.length) break;

        var next = [];

        graphLinks.forEach(function(link) {

          var from = direction === "forward"
            ? link.source
            : link.target;

          var to = direction === "forward"
            ? link.target
            : link.source;

          if (frontier.indexOf(from) !== -1) {

            selectedLinks.add(link);

            if (!visited.has(to)) {

              visited.add(to);
              next.push(to);
            }
          }
        });

        frontier = next;
      }
    }

    traverse("forward");
    traverse("backward");

    return selectedLinks;
  }


  // ---- D. Apply node or link highlighting ----

  function paint(kind, id) {

    var visibleLinks = new Set();
    var endpointIds = new Set();

    if (kind === "node") {

      var node = chart.nodes().filter(function(n) {
        return n.name === id;
      })[0];

      if (node) {
        visibleLinks = traceConnections(node);
      }

    } else if (kind === "link") {

      graphLinks.forEach(function(link) {

        if (link.connectionId === id) {

          visibleLinks.add(link);

          endpointIds.add(link.source.name);
          endpointIds.add(link.target.name);
        }
      });
    }

    paths
      .style("stroke-width", function(link) {

        return visibleLinks.has(link)
          ? "5px"
          : defaultWidth + "px";
      })

      .style("stroke-opacity", function(link) {

        if (!kind) return defaultOpacity;

        return visibleLinks.has(link)
          ? 0.95
          : 0.025;
      });

    graphNodes

      .classed("selected-node", function(n) {

        return kind === "node" &&
          nodeId(n) === id;
      })

      .classed("selected-endpoint", function(n) {

        return kind === "link" &&
          endpointIds.has(nodeId(n));
      })

      .style("opacity", function(n) {

        return kind === "link" &&
          !endpointIds.has(nodeId(n))
            ? 0.2
            : 1;
      });
  }


  // ---- E. Single shared selection controller ----

  function choose(kind, id) {

    if (
      chosen.kind === kind &&
      chosen.id === id
    ) {

      chosen = {
        kind: "",
        id: ""
      };

    } else {

      chosen = {
        kind: kind,
        id: id
      };
    }

    paint(
      chosen.kind,
      chosen.id
    );

    Shiny.setInputValue(
      "selected_element",
      chosen,
      {priority: "event"}
    );
  }


  // ---- F. Preserve original requirement presentation ----

  group.selectAll("g.node")

    .filter(function(d) {

      return data.solutionDerived.indexOf(d.name) >= 0;
    })

    .select("rect")
    .style("stroke-dasharray", "none")
    .style("stroke-width", "1px");


  // ---- G. Preserve four column headings ----

  var width = chart.size()[0];
  var height = chart.size()[1];
  var step = (width - chart.nodeWidth()) / 3;

  var headings = [

    {
      text: "Problems",
      color: "#F2D6D3"
    },

    {
      text: "Solution requirements",
      color: "#FFCC00"
    },

    {
      text: "Design principles",
      color: "#9ACD32"
    },

    {
      text: "Artefact features",
      color: "#B69AD1"
    }
  ];

  svg.attr(
    "viewBox",
    "0 -50 " + (width + 40) + " " + (height + 90)
  );

  var titleLayer = group.append("g")
    .attr("class", "column-headings")
    .style("pointer-events", "none");

  headings.forEach(function(item, i) {

    var headingX = i === 3
      ? width - 205
      : i * step;

    var heading = titleLayer.append("g")
      .attr(
        "transform",
        "translate(" + headingX + ",-42)"
      );

    heading.append("rect")
      .attr("width", 205)
      .attr("height", 30)
      .attr("rx", 4)
      .attr("ry", 4)
      .style("fill", item.color)
      .style("stroke", "#777777");

    heading.append("text")
      .attr("x", 10)
      .attr("y", 20)
      .style("fill", "#222222")
      .style("font-family", "Arial, sans-serif")
      .style("font-size", "14px")
      .style("font-weight", "bold")
      .text(item.text);
  });


  // ---- H. Preserve immediate node tooltip ----

  d3.select(el).style(
    "position",
    "relative"
  );

  var tooltip = d3.select(el)
    .append("div")
    .attr("class", "node-hover-tooltip")
    .style("position", "absolute")
    .style("display", "none")
    .style("pointer-events", "none")
    .style("z-index", "1000")
    .style("background", "#fff")
    .style("color", "#222")
    .style("border", "1px solid #aaa")
    .style("border-radius", "5px")
    .style("padding", "10px 12px")
    .style("max-width", "320px")
    .style("font-size", "13px")
    .style("line-height", "1.5")
    .style("white-space", "pre-line")
    .style("box-shadow", "0 2px 8px rgba(0,0,0,.15)");

  function positionTooltip() {

    var pos = d3.mouse(el);

    var left = pos[0] + 14;
    var top = pos[1] + 14;

    if (left > el.clientWidth - 340) {
      left = pos[0] - 335;
    }

    if (top > el.clientHeight - 150) {
      top = pos[1] - 145;
    }

    tooltip
      .style("left", Math.max(0, left) + "px")
      .style("top", Math.max(0, top) + "px");
  }


  // ---- I. Node hover and click selection ----

  graphNodes.selectAll("title").remove();

  graphNodes
    .style("cursor", "pointer")

    .on("mouseover.book", function(d) {

      if (!chosen.kind) {
        paint("node", nodeId(d));
      }

      var id = nodeId(d);

      var content =
        id + " | " +
        (data.categories[id] || "Unknown") +
        "\\n" +
        (data.labels[id] || id);

      if (
        data.solutionDerived.indexOf(id) >= 0
      ) {

        content +=
          "\\n\\nOrigin: " +
          data.originExplanation;
      }

      if (id === "PR6") {
        content += "\\n\\nNo mapped requirements.";
      }

      tooltip
        .text(content)
        .style("display", "block");

      positionTooltip();
    })

    .on("mousemove.book", positionTooltip)

    .on("mouseout.book", function() {

      tooltip.style("display", "none");

      if (!chosen.kind) {
        paint("", "");
      }
    })

    .on("click.book", function(d) {

      if (
        d3.event.button !== 0 ||
        d3.event.defaultPrevented
      ) {
        return;
      }

      choose("node", nodeId(d));

      d3.event.stopPropagation();
    });


  // ---- J. Individual connection selection ----

  // Connection IDs were added by sankey.R.
  // Invisible hit areas do not change displayed widths.

  paths.each(function(link) {

    group.insert("path", "g.node")
      .datum(link)
      .attr("class", "connection-hit-area")
      .attr("d", chart.link())
      .style("fill", "none")
      .style("stroke", "rgba(0,0,0,0.001)")
      .style("stroke-width", "12px")
      .style("pointer-events", "stroke")
      .style("cursor", "pointer");
  });

  group.selectAll("path.connection-hit-area")

    .on("mouseover.book", function(link) {

      if (!chosen.kind) {
        paint("link", link.connectionId);
      }
    })

    .on("mouseout.book", function() {

      if (!chosen.kind) {
        paint("", "");
      }
    })

    .on("click.book", function(link) {

      if (
        d3.event.button !== 0 ||
        d3.event.defaultPrevented
      ) {
        return;
      }

      choose(
        "link",
        link.connectionId
      );

      d3.event.stopPropagation();
    });


  // ---- K. Select connections from the side panel ----

  Shiny.addCustomMessageHandler(
    "select_book_connection",
    function(message) {

      choose("link", message.id);
    }
  );

}
  ',

data = list(
  labels = as.list(node_labels),
  categories = as.list(node_categories),
  solutionDerived = solution_derived,
  originExplanation = origin_explanation
)
)


# ---- 7. User interface ----



ui <- fluidPage(
  
  tags$head(
    
    tags$style(HTML('

      html {
        scroll-behavior: smooth;
      }

      body {
        background: #f7f8fa;
        font-family: Arial, sans-serif;
        color: #222;
      }

      .container-fluid {
        padding: 0;
      }

      .intro-screen {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        padding: 55px 7% 20px;
        background: #fff;
      }


/* Landing artwork */

.intro-screen {
  position: relative;
  overflow: hidden;
  isolation: isolate;
}

.intro-screen::before,
.intro-screen::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  width: 30%;
  background-image: url("landing-art.png");
  background-repeat: no-repeat;
  background-size: auto 95%;
  opacity: 0.65;
  pointer-events: none;
  z-index: -1;
}

/* Pink and yellow artwork on the left */

.intro-screen::before {
  left: 0;
  background-position: 10% center;

  -webkit-mask-image: linear-gradient(
    to right,
    black 0%,
    black 20%,
    transparent 100%
  );

  mask-image: linear-gradient(
    to right,
    black 0%,
    black 20%,
    transparent 100%
  );
}

/* Green and purple artwork on the right */

.intro-screen::after {
  right: 0;
  background-position: 90% center;

  -webkit-mask-image: linear-gradient(
    to left,
    black 0%,
    black 20%,
    transparent 100%
  );

  mask-image: linear-gradient(
    to left,
    black 0%,
    black 20%,
    transparent 100%
  );
}

.intro-content,
.scroll-cue {
  position: relative;
  z-index: 1;
}


      .intro-content {
        max-width: 1000px;
        margin: 0 auto;
        width: 100%;
      }

      .intro-eyebrow {
        color: #777;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: .12em;
        margin-bottom: 15px;
      }

      .intro-screen h1 {
        font-size: 38px;
        font-weight: 700;
        margin: 0 0 14px;
      }

      .intro-screen h2 {
        font-size: 21px;
        margin: 28px 0 12px;
      }

      .intro-screen p {
        line-height: 1.7;
        font-size: 15px;
      }

      .intro-byline {
        color: #666;
        margin-bottom: 24px;
      }

      .scroll-cue {
        margin: auto auto 0;
        padding: 22px 10px 8px;
        text-align: center;
        color: #333;
        text-decoration: none;
      }

      .scroll-cue:hover {
        color: #111;
        text-decoration: none;
      }

      .scroll-chevron {
        display: block;
        font-size: 34px;
      }

      .book-navigation {
        position: sticky;
        top: 0;
        z-index: 1020;
        display: flex;
        flex-wrap: wrap;
        gap: 24px;
        padding: 12px 7%;
        background: rgba(255, 255, 255, .96);
        border-bottom: 1px solid #e5e5e5;
      }

      .book-navigation a,
      .intro-demo-link,
      .media-card a {
        color: #23608a;
        text-decoration: none;
      }

      .book-navigation a:hover,
      .intro-demo-link:hover,
      .media-card a:hover {
        text-decoration: underline;
      }

      #introduction,
      #traceability-section,
      #demonstration-section {
        scroll-margin-top: 50px;
      }

      .intro-demo-link {
        display: inline-block;
        margin-top: 8px;
        font-size: 15px;
      }

      .graph-screen {
        padding: 20px;
      }

      .demo-screen {
        padding: 35px 7% 60px;
        background: #fff;
      }

      .demo-content {
        max-width: 1160px;
        margin: 0 auto;
      }

      .media-card {
        padding: 20px;
        margin: 20px 0;
        border: 1px solid #ddd;
        border-radius: 6px;
        background: white;
      }

      .media-card h3 {
        margin-top: 0;
      }

      .media-video {
        display: block;
        width: 100%;
        background: #111;
        border-radius: 4px;
      }

      .graph-header {
        margin: 10px 0 16px;
      }

      .muted {
        color: #666;
      }

      .diagram-container {
        background: white;
        border: 1px solid #ddd;
        border-radius: 6px;
        overflow: auto;
        height: calc(100vh - 160px);
        min-height: 650px;
      }

      .details-panel {
        background: white;
        border: 1px solid #ddd;
        border-radius: 6px;
        padding: 16px;
        height: calc(100vh - 160px);
        min-height: 650px;
        overflow-y: auto;
      }

      .details-panel h4 {
        margin-top: 12px;
      }

      .details-panel ul {
        padding-left: 22px;
      }

      .details-panel li {
        margin-bottom: 7px;
        line-height: 1.5;
      }

      .selected-node rect,
      .selected-endpoint rect {
        stroke: #222 !important;
        stroke-width: 3px !important;
        filter: drop-shadow(0 0 4px #2228);
      }

      .section-button,
      .node-title-button,
      .connection-button {
        display: block;
        background: none;
        border: none;
        padding: 3px 0;
        text-align: left;
        cursor: pointer;
      }

      .section-button {
        color: #23608a;
        font-size: 13px;
        line-height: 1.45;
      }

      .node-title-button {
        color: #222;
        font-size: 17px;
        font-weight: bold;
      }

      .connection-button {
        color: #23608a;
        font-size: 14px;
        font-weight: bold;
      }

      .section-button:hover,
      .node-title-button:hover,
      .connection-button:hover {
        text-decoration: underline;
      }

      .section-role {
        text-transform: uppercase;
        color: #666;
        font-size: 11px;
        margin-top: 12px;
        letter-spacing: .05em;
      }

      .connection-card {
        border-top: 1px solid #ddd;
        padding: 13px 0;
      }

      .mapping-line {
        margin: 10px 0;
      }

      .summary-row {
        border-bottom: 1px solid #eee;
        padding: 6px 0;
      }

      .controls-area {
        position: fixed;
        top: 16px;
        right: 20px;
        z-index: 1030;
      }

      .controls-button {
        background: white;
        border: 1px solid #aaa;
        border-radius: 22px;
        padding: 7px 13px;
      }

      .controls-popover {
        display: none;
        position: absolute;
        top: 42px;
        right: 0;
        width: 320px;
        max-width: 90vw;
        background: white;
        border: 1px solid #ccc;
        border-radius: 6px;
        padding: 14px;
        box-shadow: 0 4px 18px #0002;
      }

      .controls-popover.is-open {
        display: block;
      }

      .controls-popover li {
        margin-bottom: 8px;
      }

      .modal-dialog {
        width: calc(100% - 40px);
        max-width: 980px;
      }

      .modal-body {
        max-height: 76vh;
        overflow-y: auto;
        padding: 24px 30px;
      }

      .reader-activity {
        padding-top: 14px;
        border-top: 1px solid #ddd;
      }

      .reader-role {
        font-size: 15px;
        color: #555;
        margin: 16px 0;
      }

      .reader-section {
        padding: 0 0 18px;
        margin-bottom: 22px;
        border-bottom: 1px solid #eee;
        line-height: 1.7;
      }

      .reader-section h4 {
        font-weight: bold;
        margin: 12px 0;
      }

      .reader-section p {
        line-height: 1.7;
        margin-bottom: 13px;
      }

      .reader-section li {
        margin-bottom: 8px;
      }

      .thesis-citation {
        text-decoration: underline;
        color: #27678d;
      }

      @media (max-width: 991px) {

        .details-panel {
          height: auto;
          max-height: 65vh;
          min-height: 250px;
          margin-top: 15px;
        }
      }

    ')),
    
    tags$script(HTML('

      window.bookRead = function(kind, id) {

        Shiny.setInputValue(
          "reader_request",
          {kind: kind, id: id},
          {priority: "event"}
        );
      };

      window.bookSelectLink = function(id) {

        Shiny.setInputValue(
          "panel_link_select",
          id,
          {priority: "event"}
        );
      };

      $(document).on(
        "click",
        "#controls_toggle",
        function(e) {

          e.stopPropagation();

          $("#controls_popover").toggleClass(
            "is-open"
          );
        }
      );

      $(document).on("click", function(e) {

        if (
          !$(e.target).closest("#controls_area").length
        ) {

          $("#controls_popover").removeClass(
            "is-open"
          );
        }
      });

      $(document).on("keydown", function(e) {

        if (e.key === "Escape") {

          $("#controls_popover").removeClass(
            "is-open"
          );
        }
      });

    '))
  ),
  
  
  # ---- Section navigation ----
  
  div(
    class = "book-navigation",
    tags$a(href = "#introduction", "Introduction"),
    tags$a(href = "#traceability-section", "Traceability"),
    tags$a(href = "#demonstration-section", "Demonstration")
  ),
  
  
  # ---- Controls ----
  
  div(
    id = "controls_area",
    class = "controls-area",
    
    tags$button(
      id = "controls_toggle",
      type = "button",
      class = "controls-button",
      "? Controls"
    ),
    
    div(
      id = "controls_popover",
      class = "controls-popover",
      
      h4("Graph controls"),
      
      tags$ul(
        
        tags$li(
          "Hover over a node to preview its connected pathways."
        ),
        
        tags$li(
          "Click a node to select its three-degree pathways."
        ),
        
        tags$li(
          "Click a connection to select only that link and its endpoints."
        ),
        
        tags$li(
          "Click a section title to read the original thesis passage."
        ),
        
        tags$li(
          "Click a node title to read all associated sections by activity."
        ),
        
        tags$li(
          "Drag to pan; scroll to zoom the diagram."
        ),
        
        tags$li(
          "Click the selected element again to deselect."
        )
      )
    )
  ),
  
  
  # ---- Introductory page ----
  
  div(
    id = "introduction",
    class = "intro-screen",
    
    div(
      class = "intro-content",
      
      div(
        class = "intro-eyebrow",
        "Master's thesis · Interactive edition"
      ),
      
      h1("Design and Development of a Dual-Facing Clinical Decision Support System for Shared Decision-Making in Prosthodontics"),
      
      div(
        class = "intro-byline",
        "Patrick Michael · Technische Hochschule Deggendorf"
      ),
      
      h2("Abstract"),
      
      div(
        class = "abstract-content",
        HTML(section_body("abstract"))
      ),
      
      h2("About this interactive edition"),
      
      p(
        paste(
          "This interactive edition of the thesis allows readers",
          "to explore the relationships between the identified problems,",
          "solution requirements, design principles, and implemented features."
        )
      ),
      
      p(
        paste(
          "The Sankey diagram provides a visual overview of these",
          "connections. Each element can be explored individually,",
          "with direct access to the corresponding thesis sections,",
          "explanations, and supporting references."
        )
      ),
      
      p(
        paste(
          "Readers can navigate the research freely, following the",
          "connections in either direction and examining the original",
          "text wherever further detail is needed."
        )
      ),
      
      p(
        paste(
          "Readers can also explore the demonstrated CDSS prototype",
          "through recorded videos, a comprehensive system walkthrough,",
          "and an example After-Visit Summary (AVS)."
        )
      ),
      
      tags$a(
        href = "#demonstration-section",
        class = "intro-demo-link",
        "View demonstration"
      )
     ),
    
    tags$a(
      href = "#traceability-section",
      class = "scroll-cue",
      
      tags$span(
        class = "scroll-chevron",
        HTML("&#8964;")
      ),
      
      "Explore the research"
    )
  ),
  
  
  # ---- Interactive graph ----
  
  div(
    id = "traceability-section",
    class = "graph-screen",
    
    div(
      class = "graph-header",
      
      h2("CDSS Traceability Mapping"),
      
      p(
        class = "muted",
        paste(
          "Problems → Solution Requirements →",
          "Design Principles → Artefact Features"
        )
      )
    ),
    
    fluidRow(
      
      column(
        width = 9,
        
        div(
          class = "diagram-container",
          
          networkD3::sankeyNetworkOutput(
            "traceability",
            width = "1600px",
            height = "1100px"
          )
        )
      ),
      
      column(
        width = 3,
        
        div(
          class = "details-panel",
          
          h4("Element details"),
          
          uiOutput("element_details"),
          
          tags$hr(),
          
          h4("Mapping summary"),
          
          uiOutput("mapping_summary")
        )
      )
    )
  ),
  
  
  # ---- Demonstration materials ----
  
  div(
    id = "demonstration-section",
    class = "demo-screen",
    
    div(
      class = "demo-content",
      
      h2("Artefact demonstration"),
      
      p(
        class = "muted",
        "Explore the implemented CDSS through its walkthrough, recorded demonstrations, and example patient summary."
      ),
      
      div(
        class = "media-card",
        
        h3("System Walkthrough"),
        
        p("Full system walkthrough (PDF)."),
        
        tags$a(
          href = utils::URLencode(
            "System walkthrough.pdf",
            reserved = TRUE
          ),
          target = "_blank",
          rel = "noopener noreferrer",
          "Open walkthrough PDF in a new tab"
        )
      ),
      
      
      
      fluidRow(
        
        column(
          width = 6,
          
          div(
            class = "media-card",
            
            h3("System Launch and Treatment Overview"),
            
            p(
              paste(
                "Demonstrates launching the CDSS,",
                "selecting a clinical case, and",
                "reviewing the treatment overview."
              )
            ),
            
            tags$video(
              id = "video-launch",
              src = utils::URLencode(
                "launch - case selection - treatment overview.mp4",
                reserved = TRUE
              ),
              controls = NA,
              preload = "metadata",
              class = "media-video"
            ),
            
            tags$button(
              type = "button",
              class = "btn btn-default",
              style = "margin-top: 12px;",
              onclick = "
          var video = document.getElementById('video-launch');
          if (video.requestFullscreen) {
            video.requestFullscreen();
          } else if (video.webkitEnterFullscreen) {
            video.webkitEnterFullscreen();
          }
        ",
              "Fullscreen"
            )
          )
        ),
        
        column(
          width = 6,
          
          div(
            class = "media-card",
            
            h3("Clinical Case Editing"),
            
            p(
              "Demonstrates the case-editing workflow within the CDSS."
            ),
            
            tags$video(
              id = "video-editing",
              src = utils::URLencode(
                "case editing.mp4",
                reserved = TRUE
              ),
              controls = NA,
              preload = "metadata",
              class = "media-video"
            ),
            
            
          )
        )
      ),
      
      
      
      div(
        class = "media-card",
        
        h3("After-Visit Summary (AVS)"),
        
        p("Example after-visit summary (PDF)."),
        
        tags$a(
          href = utils::URLencode(
            "After Visit Summary.pdf",
            reserved = TRUE
          ),
          target = "_blank",
          rel = "noopener noreferrer",
          "Open AVS example PDF in a new tab"
        )
      )
    )
  )
)


# ---- 8. Shiny server ----

server <- function(input, output, session) {
  
  
  # ---- A. Render Sankey ----
  
  output$traceability <- networkD3::renderSankeyNetwork({
    shiny_sankey
  })
  
  
  # ---- B. Unified selection state ----
  
  selected_element <- reactive({
    
    x <- input$selected_element
    
    if (
      is.null(x) ||
      is.null(x$kind) ||
      !nzchar(x$kind)
    ) {
      return(NULL)
    }
    
    if (
      x$kind == "node" &&
      x$id %in% all_ids
    ) {
      return(x)
    }
    
    if (
      x$kind == "link" &&
      x$id %in% links$ConnectionID
    ) {
      return(x)
    }
    
    NULL
  })
  
  
  # ---- C. Select links from the side panel ----
  
  observeEvent(input$panel_link_select, {
    
    session$sendCustomMessage(
      "select_book_connection",
      list(id = input$panel_link_select)
    )
  })
  
  
  # ---- D. Open the thesis reader ----
  
  observeEvent(input$reader_request, {
    
    request <- input$reader_request
    
    kind <- request$kind
    id <- request$id
    
    if (
      kind == "section" &&
      id %in% sections$code
    ) {
      
      title <- section_title(id)
      
    } else if (
      kind == "node" &&
      id %in% all_ids
    ) {
      
      title <- paste0(
        id,
        ": ",
        node_labels[[id]]
      )
      
    } else {
      
      return()
    }
    
    showModal(
      modalDialog(
        
        title = title,
        
        reader_content(kind, id),
        
        footer = NULL,
        
        size = "l",
        
        easyClose = TRUE
      )
    )
  })
  
  
  # ---- E. Contextual side panel ----
  
  output$element_details <- renderUI({
    
    s <- selected_element()
    
    if (is.null(s)) {
      
      return(
        p(
          class = "muted",
          "No element selected."
        )
      )
    }
    
    
    # ---- Selected connection ----
    
    if (s$kind == "link") {
      
      row <- links[
        links$ConnectionID == s$id,
        ,
        drop = FALSE
      ]
      
      return(
        tagList(
          
          p(
            class = "muted",
            "Selected connection"
          ),
          
          h4(
            paste(
              row$Source[[1]],
              "→",
              row$Target[[1]]
            )
          ),
          
          div(
            class = "section-role",
            "Source node"
          ),
          
          node_button(
            row$Source[[1]]
          ),
          
          div(
            class = "section-role",
            "Target node"
          ),
          
          node_button(
            row$Target[[1]]
          ),
          
          tags$hr(),
          
          mapping_sections(row)
        )
      )
    }
    
    
    # ---- Selected node ----
    
    id <- s$id
    
    incoming <- links[
      links$Target == id,
      ,
      drop = FALSE
    ]
    
    outgoing <- links[
      links$Source == id,
      ,
      drop = FALSE
    ]
    
    
    # Individual connection in the side panel.
    
    connection_card <- function(row) {
      
      other <- if (row$Source[[1]] == id) {
        row$Target[[1]]
      } else {
        row$Source[[1]]
      }
      
      div(
        class = "connection-card",
        
        tags$button(
          type = "button",
          class = "connection-button",
          
          onclick = sprintf(
            "window.bookSelectLink(%s)",
            js_arg(row$ConnectionID[[1]])
          ),
          
          paste(
            row$Source[[1]],
            "→",
            row$Target[[1]]
          )
        ),
        
        div(
          class = "muted",
          node_labels[[other]]
        ),
        
        mapping_sections(row)
      )
    }
    
    
    # PR details remain original.
    # F descriptions are retrieved from the thesis CSV.
    
    details <- if (id %in% names(problem_factors)) {
      
      problem_factors[[id]]
      
    } else if (grepl("^F[0-9]+$", id)) {
      
      feature_sentences(id)
      
    } else {
      
      character(0)
    }
    
    
    tagList(
      
      node_button(id),
      
      p(
        strong("Category: "),
        get_category(id)
      ),
      
      if (length(details)) {
        
        tags$ul(
          lapply(details, tags$li)
        )
      },
      
      if (id %in% solution_derived) {
        
        p(
          strong("Requirement origin: "),
          origin_explanation
        )
      },
      
      section_links(
        node_section_codes(
          id,
          own_only = TRUE
        ),
        "Corresponding thesis sections"
      ),
      
      tags$hr(),
      
      h4(
        paste0(
          "Incoming mappings: ",
          nrow(incoming)
        )
      ),
      
      lapply(
        seq_len(nrow(incoming)),
        function(i) {
          connection_card(
            incoming[i, , drop = FALSE]
          )
        }
      ),
      
      h4(
        paste0(
          "Outgoing mappings: ",
          nrow(outgoing)
        )
      ),
      
      lapply(
        seq_len(nrow(outgoing)),
        function(i) {
          connection_card(
            outgoing[i, , drop = FALSE]
          )
        }
      )
    )
  })
  
  
  # ---- F. Original mapping summary ----
  
  output$mapping_summary <- renderUI({
    
    tagList(
      
      div(
        class = "summary-row",
        strong("Total mappings: "),
        nrow(links)
      ),
      
      div(
        class = "summary-row",
        strong("PR → R: "),
        sum(grepl("^PR", links$Source))
      ),
      
      div(
        class = "summary-row",
        strong("R → P: "),
        sum(grepl("^(R|SDM)", links$Source))
      ),
      
      div(
        class = "summary-row",
        strong("P → F: "),
        sum(grepl("^P[0-9]+$", links$Source))
      ),
      
      div(
        class = "summary-row",
        strong("Unmapped problem groups: "),
        length(
          setdiff(
            paste0("PR", 1:6),
            unique(links$Source)
          )
        )
      )
    )
  })
}


# ---- 9. Launch application ----

shinyApp(ui, server)
