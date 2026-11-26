
# ---- 1. Load libraries ----

pacman::p_load(networkD3, htmlwidgets)


# ---- 2. Load mappings ----

links <- read.csv(
  "mappings.csv",
  stringsAsFactors = FALSE,
  fileEncoding = "UTF-8-BOM"
)

stopifnot(
  all(c("Source", "Target") %in% names(links))
)


# ---- 3. Identify traceability layers ----

get_layer <- function(x) {
  ifelse(grepl("^PR[0-9]+$", x), "PR",
         ifelse(grepl("^(R[0-9]+|SDM[0-9]+)$", x), "R",
                ifelse(grepl("^P[0-9]+$", x), "P",
                       ifelse(grepl("^F[0-9]+$", x), "F", NA_character_))))
}

nodes <- data.frame(
  name = unique(c(links$Source, links$Target)),
  stringsAsFactors = FALSE
)

nodes$layer <- get_layer(nodes$name)
links$origin_layer <- get_layer(links$Source)

stopifnot(
  !anyNA(nodes$layer),
  !anyNA(links$origin_layer)
)


# ---- 4. Prepare Sankey data ----

# networkD3 uses zero-based node indices.
links$source_id <- match(links$Source, nodes$name) - 1L
links$target_id <- match(links$Target, nodes$name) - 1L

# Each mapping is a binary relationship.
links$value <- 1L


# ---- 5. Define layer colours ----

colours <- htmlwidgets::JS('
  d3.scaleOrdinal()
    .domain(["PR", "R", "P", "F"])
    .range([
      "#F2D6D3",
      "#FFCC00",
      "#9ACD32",
      "#B69AD1"
    ])
')


# ---- 6. Generate Sankey diagram ----

sankey <- networkD3::sankeyNetwork(
  Links = links,
  Nodes = nodes,
  Source = "source_id",
  Target = "target_id",
  Value = "value",
  NodeID = "name",
  NodeGroup = "layer",
  LinkGroup = "origin_layer",
  colourScale = colours,
  fontSize = 14,
  nodeWidth = 25,
  nodePadding = 15,
  width = 1600,
  height = 1100,
  sinksRight = TRUE
)


# ---- 7. Customize layout and interactivity ----

sankey <- htmlwidgets::onRender(sankey, '
function(el, x, connectionIds) {

  var chart = this.sankey;
  var width = chart.size()[0];
  var height = chart.size()[1];
  var nodeWidth = chart.nodeWidth();

  var svg = d3.select(el).select("svg");
  var group = svg.select("g");


  // ---- A. Identify the four layers ----

  var layers = {
    PR: [],
    R: [],
    P: [],
    F: []
  };

  var layerNames = ["PR", "R", "P", "F"];

  function getLayer(name) {
    if (/^PR[0-9]+$/.test(name)) return "PR";

    if (/^(R[0-9]+|SDM[0-9]+)$/.test(name)) {
      return "R";
    }

    if (/^P[0-9]+$/.test(name)) return "P";
    if (/^F[0-9]+$/.test(name)) return "F";

    return null;
  }


  // ---- B. Position nodes in four fixed columns ----

  var step = (width - nodeWidth) / 3;

  chart.nodes().forEach(function(d) {
    var layer = getLayer(d.name);

    if (!layer) return;

    d.x = layerNames.indexOf(layer) * step;
    layers[layer].push(d);
  });


  // ---- C. Include PR6 without a false mapping ----

  var pr6 = {
    name: "PR6",
    x: 0,
    y: 0,
    dy: 22,
    isolated: true
  };

  layers.PR.push(pr6);


  // ---- D. Sort nodes within each layer ----

  function order(d) {

    if (/^SDM/.test(d.name)) {
      return 100 + parseInt(
        d.name.replace("SDM", ""), 10
      );
    }

    return parseInt(
      d.name.replace(/[^0-9]/g, ""), 10
    );
  }

  layerNames.forEach(function(layer) {
    layers[layer].sort(function(a, b) {
      return order(a) - order(b);
    });
  });


  // ---- E. Calculate collision-free vertical spacing ----

  var gap = 18;
  var margin = 12;
  var scale = 1;

  layerNames.forEach(function(layer) {

    var items = layers[layer];

    var fixedHeight = items.reduce(function(sum, d) {
      return sum + (d.isolated ? d.dy : 0);
    }, 0);

    var flowHeight = items.reduce(function(sum, d) {
      return sum + (d.isolated ? 0 : d.dy);
    }, 0);

    var available = height -
      2 * margin -
      gap * (items.length - 1) -
      fixedHeight;

    if (flowHeight > 0) {
      scale = Math.min(
        scale,
        Math.max(0.01, available / flowHeight)
      );
    }
  });

  // Scale nodes and links consistently.
  chart.nodes().forEach(function(d) {
    d.dy *= scale;
  });

  chart.links().forEach(function(d) {
    d.dy *= scale;
  });

  // Distribute nodes vertically within each column.
  layerNames.forEach(function(layer) {

    var items = layers[layer];

    var totalHeight = items.reduce(function(sum, d) {
      return sum + d.dy;
    }, 0) + gap * (items.length - 1);

    var y = (height - totalHeight) / 2;

    items.forEach(function(d) {
      d.y = y;
      y += d.dy + gap;
    });
  });

  chart.relayout();


  // ---- F. Update node positions and labels ----

  group.selectAll("g.node")
    .attr("transform", function(d) {
      return "translate(" + d.x + "," + d.y + ")";
    });

  group.selectAll("g.node rect")
    .attr("height", function(d) {
      return d.dy;
    });

  group.selectAll("g.node text")
    .attr("y", function(d) {
      return d.dy / 2;
    })
    .attr("x", function(d) {
      return d.x < width / 2
        ? nodeWidth + 6
        : -6;
    })
    .attr("text-anchor", function(d) {
      return d.x < width / 2
        ? "start"
        : "end";
    });

  // Disable individual node dragging.
  // The four columns must remain fixed.
  group.selectAll("g.node")
    .on(".drag", null);


  // ---- G. Draw thin, layer-coloured connections ----

  var defaultWidth = 2.5;
  var defaultOpacity = 0.25;

  var paths = group.selectAll("path.link")
    .attr("d", chart.link())
    .style("fill", "none")
    .style("stroke-width", defaultWidth + "px")
    .style("stroke-opacity", defaultOpacity);

  // Associate each graphical link with its CSV ConnectionID.
  paths.attr("data-connection-id", function(d) {
    var key = d.source.name + "|" + d.target.name;
    d.connectionId = connectionIds[key];
    return d.connectionId;
  });


  // ---- H. Mark solution-derived requirements ----

  var solutionDerived = [
    "R5", "R9", "R12", "R14", "SDM2"
  ];

  group.selectAll("g.node")
    .filter(function(d) {
      return solutionDerived.indexOf(d.name) >= 0;
    })
    .select("rect")
    .style("stroke-dasharray", "5,3")
    .style("stroke-width", "2.5px");


  // ---- I. Display the isolated PR6 node ----

  var isolated = group.append("g")
    .attr("class", "unmapped-node")
    .attr(
      "transform",
      "translate(" + pr6.x + "," + pr6.y + ")"
    );

  isolated.append("rect")
    .attr("width", nodeWidth)
    .attr("height", pr6.dy)
    .style("fill", "#F2D6D3")
    .style("stroke", "#555555");

  isolated.append("text")
    .attr("x", nodeWidth + 6)
    .attr("y", pr6.dy / 2)
    .attr("dy", ".35em")
    .style("font-size", "14px")
    .text("PR6 (no mappings)");

  isolated.append("title")
    .text("PR6 has no mapped requirements.");


  // ---- J. Define three-degree pathway tracing ----

  var graphLinks = chart.links();

  function traceConnections(startNode) {

    var selectedLinks = new Set();

    function traverse(direction) {

      var visitedNodes = new Set([startNode]);
      var frontier = [startNode];

      // Follow up to three mapping relationships.
      // Forward and backward searches remain separate.

      for (var depth = 0; depth < 3; depth++) {

        if (frontier.length === 0) break;

        var nextFrontier = [];

        graphLinks.forEach(function(link) {

          var fromNode;
          var toNode;

          if (direction === "forward") {
            fromNode = link.source;
            toNode = link.target;
          } else {
            fromNode = link.target;
            toNode = link.source;
          }

          if (frontier.indexOf(fromNode) !== -1) {

            selectedLinks.add(link);

            if (!visitedNodes.has(toNode)) {
              visitedNodes.add(toNode);
              nextFrontier.push(toNode);
            }
          }
        });

        frontier = nextFrontier;
      }
    }

    traverse("forward");
    traverse("backward");

    return selectedLinks;
  }


  // ---- K. Highlight pathways on node hover ----

  group.selectAll("g.node")
    .on("mouseover.traceability", function(d) {

      var highlighted = traceConnections(d);

      paths
        .style("stroke-width", function(link) {
          return highlighted.has(link)
            ? "5px"
            : defaultWidth + "px";
        })
        .style("stroke-opacity", function(link) {
          return highlighted.has(link)
            ? 0.95
            : 0.025;
        });
    })

    .on("mouseout.traceability", function() {

      paths
        .style("stroke-width", defaultWidth + "px")
        .style("stroke-opacity", defaultOpacity);
    });


  // ---- L. Configure zoom and pan ----

  svg.attr(
    "viewBox",
    "0 0 " + (width + 40) + " " + (height + 40)
  );

  // Add a transparent background so dragging
  // also works in empty areas of the diagram.
  svg.insert("rect", "g")
    .attr("class", "zoom-background")
    .attr("x", 0)
    .attr("y", 0)
    .attr("width", width + 40)
    .attr("height", height + 40)
    .style("fill", "transparent")
    .style("pointer-events", "all");

  var zoom = d3.zoom()
    .scaleExtent([0.2, 3])
    .on("zoom", function() {

      group.attr(
        "transform",
        d3.event.transform
      );
    });

  svg.call(zoom);

  // Prevent accidental double-click zooming.
  svg.on("dblclick.zoom", null);

}
',
data = as.list(stats::setNames(
  links$ConnectionID,
  paste(links$Source, links$Target, sep = "|")
))
)


# ---- 8. Display visualization ----

sankey


# ---- 9. Export standalone HTML ----

# When app.R sources this script, it sets
# options(traceability.in_shiny = TRUE).
#
# This prevents an unnecessary HTML export
# every time the Shiny application starts.

if (!isTRUE(getOption("traceability.in_shiny", FALSE))) {
  
  networkD3::saveNetwork(
    sankey,
    "traceability_sankey.html",
    selfcontained = TRUE
  )
  
}
