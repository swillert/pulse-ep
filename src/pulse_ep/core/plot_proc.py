import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from pulse_ep.core import mesh_proc as mesh_proc


def export_to_pdf(file_png, file_pdf, width, height):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(file_pdf)
    c.drawImage(file_png, 0, 0, width=width, height=height)  # Change width and height as needed
    c.save()


def create_custom_colormap(lower_limit, upper_limit):
    # Define the colors we want to use
    red = np.array([1.0, 0.0, 0.0, 1.0])
    yellow = np.array([1.0, 1.0, 0.0, 1.0])
    green = np.array([0.0, 1.0, 0.0, 1.0])
    blue = np.array([0.0, 0.0, 1.0, 1.0])
    purple = np.array([0.5, 0.0, 0.5, 1.0])
    grey = np.array([189 / 256, 189 / 256, 189 / 256, 1.0])
    black = np.array([11 / 256, 11 / 256, 11 / 256, 1.0])

    # Create the colormap
    mapping = np.linspace(lower_limit, upper_limit, 256)
    newcolors = np.empty((256, 4))
    newcolors[mapping >= lower_limit] = grey
    newcolors[mapping < lower_limit] = black
    newcolors[
        (mapping >= lower_limit + (upper_limit - lower_limit) / 5)
        & (mapping < lower_limit + 2 * (upper_limit - lower_limit) / 5)
    ] = red
    newcolors[
        (mapping >= lower_limit + 2 * (upper_limit - lower_limit) / 5)
        & (mapping < lower_limit + 3 * (upper_limit - lower_limit) / 5)
    ] = yellow
    newcolors[
        (mapping >= lower_limit + 3 * (upper_limit - lower_limit) / 5)
        & (mapping < lower_limit + 4 * (upper_limit - lower_limit) / 5)
    ] = green
    newcolors[
        (mapping >= lower_limit + 4 * (upper_limit - lower_limit) / 5) & (mapping < upper_limit)
    ] = blue
    newcolors[mapping >= upper_limit] = purple

    # Make the colormap from the listed colors
    cmap = ListedColormap(newcolors)
    return cmap


def create_modified_hsv_colormap():
    # Create a  colormap
    # cmap = plot_proc.create_custom_colormap(np.nanmin(sim_data)-10, np.nanmax(sim_data)+10)

    # Get the hsv colormap from matplotlib
    cMap = plt.cm.get_cmap("hsv", 1024)

    # Create an array of the colormap colors
    colors = cMap(np.linspace(0, 1, 1024))

    # Remove the last 9 colors
    newcolors = colors[:-9, :3]  # We slice here to get only the RGB values, ignore the alpha value.

    # Add white color for values below clim
    newcolors[-1:] = [1.0, 1.0, 1.0]  # Set first 20% of colors to white

    # Flip the colormap
    newcolors = newcolors[::-1]

    # Get the colors 'magenta' and 'red'
    magenta = newcolors[-1]  # last color  # noqa: F841
    red = newcolors[0]  # first color  # noqa: F841

    # Create a new colormap from the remaining colors
    cmap = plt.cm.colors.ListedColormap(newcolors)

    return cmap


def plot_histogram(
    face_scalars, face_areas, study_name, map_name, min_value=None, max_value=None, step_size=5
):
    """
    Plot a histogram based on face_scalars and face_areas.

    :param face_scalars: Array of face scalars.
    :param face_areas: Array of face areas.
    :param study_name: Name of the study.
    :param map_name: Name of the map.
    :param min_value: Minimum value for the histogram bins (optional).
    :param max_value: Maximum value for the histogram bins (optional).
    :param step_size: Step size for the histogram bins (default: 5).
    :return: Tuple containing the matplotlib figure, axes, and histogram values.
    """
    # Set the bin range based on the provided min_value, max_value, and step_size
    if min_value is None:
        min_value = np.min(face_scalars)
    if max_value is None:
        max_value = np.max(face_scalars)

    bins = np.arange(min_value, max_value + step_size + 1, step_size)

    # Categorize face_area based on face_scalar
    hist, _ = np.histogram(face_scalars, bins=bins, weights=face_areas)

    # Create a new figure and axes
    fig, ax = plt.subplots()

    # Plot the histogram
    plt.title(study_name + "/" + map_name)
    plt.bar(bins[:-1], hist, width=step_size, align="edge")
    plt.xlabel("Similarity [%]")
    plt.yscale("log")  # Set y-axis scale to logarithmic
    plt.ylabel("Area [$cm^2$] (log scale)")

    return fig, ax, hist
