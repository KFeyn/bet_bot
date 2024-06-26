import matplotlib.pyplot as plt
import matplotlib
import typing as tp
import io

matplotlib.use('Agg')


def get_color(row) -> tp.Tuple[str, str]:
    if row[1] > row[2] or (row[1] == row[2] and row[5] == 1):
        return 'green', 'red'
    elif row[1] < row[2] or (row[1] == row[2] and row[5] == 2):
        return 'red', 'green'
    else:
        return 'yellow', 'yellow'


async def make_plot(table_data: tp.List[tp.List], name: str) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axis('off')

    table = ax.table(cellText=table_data, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.2, 1.2)

    for i, row in enumerate(table_data[1:], start=1):
        color1, color2 = get_color(row)
        table[(i, 0)].set_facecolor(color1)
        table[(i, 3)].set_facecolor(color2)

    plt.title(name)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)

    plt.close(fig)

    return buf
