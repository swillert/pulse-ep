# pulse_ep_demo.R — End-to-end example.
#
# What this does:
#   1. Logs in and lists the studies in the database.
#   2. Picks the first map in the first study (override with PE_MAP_ID).
#   3. Plots the triangulated chamber mesh in 3D with `rgl`.
#   4. Plots the per-vertex scalar distribution with `ggplot2`.
#
# Run:
#   Rscript pulse_ep_demo.R
#
# Requires PULSE_EP_BASE_URL / PULSE_EP_USERNAME / PULSE_EP_PASSWORD
# in the environment (see ../README.md).

suppressPackageStartupMessages({
  library(ggplot2)
  library(tibble)
})

source("pulse_ep_client.R")

# --- 1. Login & navigation ----------------------------------------------
token <- pe_login()
studies <- pe_list_studies(token)
if (nrow(studies) == 0) stop("No studies in the database.")
cat(sprintf("Found %d study/studies.\n", nrow(studies)))
print(head(studies, 5))

map_id_env <- Sys.getenv("PE_MAP_ID", unset = "")
if (nzchar(map_id_env)) {
  map_id <- as.integer(map_id_env)
  cat(sprintf("Using PE_MAP_ID = %d from environment.\n", map_id))
} else {
  maps <- pe_list_maps(token, study_id = studies$id[1])
  if (nrow(maps) == 0) stop("Study has no EP maps.")
  map_id <- maps$id[1]
  cat(sprintf("Using first map of first study: id=%d (\"%s\")\n",
              map_id, maps$map_name[1]))
}

# --- 2. Fetch mesh -------------------------------------------------------
mesh <- pe_get_mesh(token, map_id = map_id,
                    scalar_name = NULL, distance = 5.0)
cat(sprintf("Mesh: %d vertices, %d triangles, scalar non-NA = %d/%d.\n",
            nrow(mesh$vertices), nrow(mesh$faces),
            sum(!is.na(mesh$scalars)), length(mesh$scalars)))

# --- 3. 3D mesh in rgl (optional — comment out if no OpenGL) -----------
if (requireNamespace("rgl", quietly = TRUE)) {
  rgl::open3d()
  rgl::triangles3d(
    x = mesh$vertices[as.vector(t(mesh$faces)), 1],
    y = mesh$vertices[as.vector(t(mesh$faces)), 2],
    z = mesh$vertices[as.vector(t(mesh$faces)), 3],
    color = rep(mesh$scalars, each = 3),
    alpha = 0.9
  )
  rgl::title3d(main = sprintf("pulse-ep map %d", map_id))
  message("rgl scene open. Close it to continue.")
}

# --- 4. Scalar distribution (ggplot2) -----------------------------------
df <- tibble(scalar = mesh$scalars)
p <- ggplot(df, aes(x = scalar)) +
  geom_histogram(bins = 40, fill = "#3a76ff", colour = "white") +
  labs(title = sprintf("pulse-ep map %d — scalar distribution", map_id),
       x = "Scalar value", y = "Vertex count") +
  theme_minimal()
print(p)
ggsave("pulse_ep_demo_histogram.png", p, width = 6, height = 4, dpi = 150)
cat("Wrote pulse_ep_demo_histogram.png\n")
