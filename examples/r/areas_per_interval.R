# areas_per_interval.R — second cross-language reproducibility demo.
#
# Calls /calculate_areas_for_intervals on a pulse-ep server and reports
# the surface area per score bin as both a table and a bar plot. This
# is exactly the reduction the bundled web viewer and the clinical
# Excel reports compute; doing it in R from the raw REST payload proves
# the platform is faithful across stacks.
#
# Run:
#   Rscript areas_per_interval.R
#
# Optional env overrides:
#   PE_MAP_ID       integer, map to analyse (default: first map of first study)
#   PE_SCALAR_NAME  default "act"
#   PE_DISTANCE_MM  default 5.0

suppressPackageStartupMessages({
  library(ggplot2)
  library(tibble)
})

source("pulse_ep_client.R")

# --- 1. Connection & target map -----------------------------------------
token <- pe_login()
studies <- pe_list_studies(token)
if (nrow(studies) == 0) stop("No studies in the database.")

map_id_env <- Sys.getenv("PE_MAP_ID", unset = "")
if (nzchar(map_id_env)) {
  map_id <- as.integer(map_id_env)
} else {
  maps <- pe_list_maps(token, study_id = studies$id[1])
  if (nrow(maps) == 0) stop("First study has no EP maps.")
  map_id <- maps$id[1]
}
scalar_name <- Sys.getenv("PE_SCALAR_NAME", unset = "act")
distance_mm <- as.numeric(Sys.getenv("PE_DISTANCE_MM", unset = "5.0"))
cat(sprintf("map_id=%d  scalar=%s  distance=%.1f mm\n",
            map_id, scalar_name, distance_mm))

# --- 2. Define score bins ----------------------------------------------
# The default clinical bins for pace-mapping similarity scores.
# Override here for your own colormap intervals if needed.
interval_breaks <- c(50, 60, 70, 80, 90, 100)
intervals <- mapply(c, head(interval_breaks, -1), tail(interval_breaks, -1),
                   SIMPLIFY = FALSE)
labels <- sprintf("%g–%g", head(interval_breaks, -1), tail(interval_breaks, -1))

# --- 3. Call the platform endpoint -------------------------------------
areas_cm2 <- pe_areas_per_interval(
  token, map_id = map_id, intervals = intervals,
  scalar_name = scalar_name, distance = distance_mm
)

df <- tibble(
  interval  = factor(labels, levels = labels),
  area_cm2  = areas_cm2
)
cat("\nArea per score interval (cm^2):\n")
print(df)

total <- sum(df$area_cm2, na.rm = TRUE)
cat(sprintf("\nTotal covered area = %.3f cm^2\n", total))

# --- 4. Bar plot --------------------------------------------------------
p <- ggplot(df, aes(x = interval, y = area_cm2)) +
  geom_col(fill = "#3a76ff") +
  labs(title = sprintf("Map %d — area per %s score interval", map_id, scalar_name),
       subtitle = sprintf("interpolation radius = %.1f mm", distance_mm),
       x = "Score interval [%]", y = expression(Area ~ "[" ~ cm^2 ~ "]")) +
  theme_minimal()
print(p)
ggsave("areas_per_interval.png", p, width = 6, height = 4, dpi = 150)
cat("\nWrote areas_per_interval.png\n")
