# pulse_ep_client.R — Minimal REST client for pulse-ep, built on httr2.
#
# Usage:
#   source("pulse_ep_client.R")
#   token  <- pe_login()                       # reads env vars
#   studies <- pe_list_studies(token)
#   maps    <- pe_list_maps(token, study_id = studies$id[1])
#   mesh    <- pe_get_mesh(token, map_id = maps$id[1])

suppressPackageStartupMessages({
  library(httr2)
  library(jsonlite)
})

#' Resolve the pulse-ep base URL, honoring the PULSE_EP_BASE_URL env var.
pe_base_url <- function(base_url = NULL) {
  if (!is.null(base_url) && nzchar(base_url)) return(base_url)
  env <- Sys.getenv("PULSE_EP_BASE_URL", unset = "")
  if (!nzchar(env)) {
    stop(
      "pulse-ep base URL is not set. Pass `base_url=` or export ",
      "PULSE_EP_BASE_URL.",
      call. = FALSE
    )
  }
  env
}

#' Exchange username/password for a JWT access token.
pe_login <- function(username = Sys.getenv("PULSE_EP_USERNAME"),
                     password = Sys.getenv("PULSE_EP_PASSWORD"),
                     base_url = NULL) {
  if (!nzchar(username) || !nzchar(password)) {
    stop(
      "PULSE_EP_USERNAME / PULSE_EP_PASSWORD are not set in the env.",
      call. = FALSE
    )
  }
  resp <- request(pe_base_url(base_url)) |>
    req_url_path("/login_user") |>
    req_method("POST") |>
    req_headers("Content-Type" = "application/json") |>
    req_body_raw(toJSON(list(username = username, password = password),
                       auto_unbox = TRUE)) |>
    req_perform()
  resp_body_json(resp)$access_token
}

#' Internal: GET helper that adds the Bearer token.
.pe_get <- function(token, path, query = list(), base_url = NULL) {
  req <- request(pe_base_url(base_url)) |>
    req_url_path(path) |>
    req_headers(Authorization = paste("Bearer", token))
  if (length(query) > 0) req <- req_url_query(req, !!!query)
  resp_body_json(req_perform(req), simplifyVector = TRUE)
}

#' List all studies. Returns a data.frame with columns `id` and `study_name`.
pe_list_studies <- function(token, base_url = NULL) {
  data <- .pe_get(token, "/list_studies", base_url = base_url)
  if (length(data) == 0) return(data.frame(id = integer(), study_name = character()))
  as.data.frame(data, stringsAsFactors = FALSE)
}

#' List the EP maps belonging to one study.
pe_list_maps <- function(token, study_id, base_url = NULL) {
  data <- .pe_get(token, paste0("/list_epmaps_in_study/", study_id),
                  base_url = base_url)
  if (length(data) == 0) return(data.frame())
  as.data.frame(data, stringsAsFactors = FALSE)
}

#' Call /calculate_areas_for_intervals — surface area per score bin.
#'
#' `intervals` is a list of length-2 numeric vectors, e.g.
#'   list(c(50, 60), c(60, 70), c(70, 80), c(80, 90), c(90, 100)).
#' Returns a numeric vector of areas in cm^2, NA for empty bins.
pe_areas_per_interval <- function(token, map_id, intervals,
                                  scalar_name = NULL, distance = 5.0,
                                  base_url = NULL) {
  payload <- list(
    map_id      = map_id,
    scalar_name = scalar_name,
    distance    = distance,
    intervals   = intervals
  )
  resp <- request(pe_base_url(base_url)) |>
    req_url_path("/calculate_areas_for_intervals") |>
    req_method("POST") |>
    req_headers(Authorization = paste("Bearer", token),
                "Content-Type" = "application/json") |>
    req_body_raw(toJSON(payload, auto_unbox = TRUE)) |>
    req_perform()
  data <- resp_body_json(resp, simplifyVector = TRUE)
  as.numeric(unlist(data$areas))
}

#' Fetch the mesh (vertices, triangles, scalars) for one map.
#' Returns a list with `vertices`, `faces`, `scalars`, `normalized`,
#' `points` and `point_scalars`.
`%||%` <- function(a, b) if (is.null(a)) b else a

#' Quantities a map carries: name, kind and unit, plus the primary one.
#' Clients should read the choice from here rather than assuming a field name.
pe_map_scalars <- function(token, map_id) {
  req <- request(paste0(pe_base_url(), "/epmaps/", map_id, "/scalars")) |>
    req_headers(Authorization = paste("Bearer", token))
  resp <- req_perform(req)
  out <- resp_body_json(resp, simplifyVector = TRUE)
  out
}

pe_get_mesh <- function(token, map_id, scalar_name = NULL,
                        distance = 5.0, base_url = NULL) {
  data <- .pe_get(
    token, "/get_mesh_data",
    query = list(
      map_id = map_id, scalar_name = scalar_name, distance = distance
    ),
    base_url = base_url
  )
  md <- data$mesh_data
  pd <- data$point_data
  list(
    vertices       = matrix(unlist(md$vertices), ncol = 3, byrow = TRUE),
    faces          = matrix(unlist(md$faces),    ncol = 3, byrow = TRUE) + 1L,  # R is 1-indexed
    scalars        = as.numeric(md$scalar_data),
    normalized     = as.numeric(md$normalized_scalar_data),
    # An empty JSON array arrives as an empty *list*, not NULL, so a
    # !is.null() guard lets it through and matrix() then fails on the NULL
    # that unlist() returns. A map may legitimately have no acquisition
    # points: an EnSiteX mesh carrying only per-vertex fields has none.
    points         = if (length(pd$coordinates) > 0)
                       matrix(unlist(pd$coordinates), ncol = 3, byrow = TRUE)
                     else matrix(numeric(), ncol = 3),
    point_scalars  = as.numeric(pd$scalar_data)
  )
}
