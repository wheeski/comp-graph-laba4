import math
import os
import re
import struct
import time
import tkinter as tk
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox, ttk


METHODS = ('Уравнение окружности', 'Параметрическое уравнение',
           'Алгоритм Брезенхема', 'Встроенные средства')
COLORS = ((220, 55, 55), (30, 110, 210))


def nearest(value):
    return math.floor(value + 0.5)


def symmetric_points(cx, cy, x, y):
    return {(cx + dx, cy + dy) for dx, dy in
            ((x, y), (y, x), (-x, y), (-y, x),
             (x, -y), (y, -x), (-x, -y), (-y, -x))}


def equation_circle(cx, cy, radius):
    points = set()
    for x in range(nearest(radius / math.sqrt(2)) + 1):
        y = nearest(math.sqrt(max(0, radius * radius - x * x)))
        points.update(symmetric_points(cx, cy, x, y))
    return points


def parametric_circle(cx, cy, radius):
    points = set()
    steps = max(1, math.ceil(2 * math.pi * radius))
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        points.add((cx + nearest(radius * math.cos(angle)),
                    cy + nearest(radius * math.sin(angle))))
    return points


def bresenham_circle(cx, cy, radius):
    points = set()
    x, y = 0, radius
    decision = 3 - 2 * radius
    while x <= y:
        points.update(symmetric_points(cx, cy, x, y))
        if decision < 0:
            decision += 4 * x + 6
        else:
            decision += 4 * (x - y) + 10
            y -= 1
        x += 1
    return points


def native_circle(cx, cy, radius, width, height):
    """Растеризация библиотечной функцией Pillow в Windows и Linux."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        raise RuntimeError(
            'Для встроенного метода установите Pillow: python -m pip install Pillow'
        ) from None
    image = Image.new('1', (width, height), 0)
    ImageDraw.Draw(image).ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        outline=1, width=1
    )
    pixels = image.load()
    return {(x, y)
            for y in range(max(0, cy - radius), min(height, cy + radius + 1))
            for x in range(max(0, cx - radius), min(width, cx + radius + 1))
            if pixels[x, y]}


def line_points(x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx + dy
    while True:
        yield x0, y0
        if (x0, y0) == (x1, y1):
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Лабораторная работа 4 — вариант 2')
        self.geometry('1400x950')
        self.minsize(920, 650)
        self.values = {key: tk.StringVar(value=value) for key, value in
                       [('width', '800'), ('height', '600'), ('cx', '400'),
                        ('cy', '300'), ('side', '260')]}
        self.show_polygon = tk.BooleanVar(value=True)
        self.svg_parameters = None
        self.current_method = 2
        self.current_data = None
        self.photo = None
        self.canvas = None
        self.width, self.height = 800, 600
        panel = ttk.Frame(self, padding=10)
        panel.pack(fill='x')
        panel.columnconfigure(0, weight=1)

        canvas_settings = ttk.LabelFrame(panel, text='Настройки холста', padding=8)
        canvas_settings.grid(row=0, column=0, sticky='ew', padx=(0, 12), pady=(0, 6))
        for col, (key, label) in enumerate((('width', 'Ширина:'), ('height', 'Высота:'))):
            ttk.Label(canvas_settings, text=label).grid(row=0, column=2 * col, padx=(0, 4))
            ttk.Entry(canvas_settings, textvariable=self.values[key], width=6).grid(
                row=0, column=2 * col + 1, padx=(0, 8))
        ttk.Button(canvas_settings, text='Создать', command=self.create_canvas).grid(row=0, column=4)

        parameters = ttk.LabelFrame(panel, text='Параметры пятиугольника', padding=8)
        parameters.grid(row=1, column=0, sticky='ew', padx=(0, 12), pady=(0, 6))
        for col, (key, label) in enumerate((('cx', 'Центр X:'), ('cy', 'Y:'))):
            ttk.Label(parameters, text=label).grid(row=0, column=2 * col, sticky='w', padx=(0, 4))
            ttk.Entry(parameters, textvariable=self.values[key], width=7).grid(
                row=0, column=2 * col + 1, sticky='w', padx=(0, 8))
        ttk.Label(parameters, text='Сторона:').grid(row=1, column=0, sticky='w', pady=(6, 0))
        ttk.Entry(parameters, textvariable=self.values['side'], width=7).grid(
            row=1, column=1, sticky='w', pady=(6, 0))

        actions = ttk.LabelFrame(panel, text='Действия', padding=8)
        actions.grid(row=2, column=0, sticky='ew', padx=(0, 12))
        for col, (label, command) in enumerate((
                ('Сохранить BMP', lambda: self.save('bmp')),
                ('Сохранить PBM', lambda: self.save('pbm')),
                ('Очистить', self.clear))):
            ttk.Button(actions, text=label, command=command).grid(row=0, column=col, padx=(0, 5))

        svg = ttk.LabelFrame(panel, text='Загрузка из SVG', padding=8)
        svg.grid(row=0, column=1, rowspan=2, sticky='new', pady=(0, 6))
        svg.columnconfigure(0, weight=1)
        ttk.Button(svg, text='Загрузить SVG', command=self.load_svg).grid(row=0, column=0, sticky='ew')
        self.svg_status = tk.StringVar(value='SVG не загружен')
        self.svg_status_label = ttk.Label(svg, textvariable=self.svg_status, foreground='#a00000', anchor='center')
        self.svg_status_label.grid(row=1, column=0, sticky='ew', pady=3)
        ttk.Button(svg, text='Отобразить на холсте', command=self.apply_svg).grid(row=2, column=0, sticky='ew')

        algorithms = ttk.LabelFrame(panel, text='Алгоритмы рисования', padding=8)
        algorithms.grid(row=2, column=1, sticky='new')
        for i, label in enumerate(('Уравнение', 'Параметрический', 'Брезенхем', 'Встроенный')):
            ttk.Button(algorithms, text=label, command=lambda m=i: self.draw(m)).grid(
                row=i // 2, column=i % 2, sticky='ew', padx=2, pady=2)
        self.drawing_area = ttk.Frame(self)
        self.drawing_area.pack(fill='both', expand=True, padx=10, pady=8)
        self.drawing_area.rowconfigure(0, weight=1)
        self.drawing_area.columnconfigure(0, weight=1)
        self.status = tk.StringVar(value='Задайте параметры и нажмите «Создать холст».')

    def parameters(self):
        try:
            width, height, cx, cy = (int(self.values[k].get()) for k in ('width', 'height', 'cx', 'cy'))
            side = float(self.values['side'].get().replace(',', '.'))
        except ValueError:
            raise ValueError('Размеры и координаты должны быть целыми числами, сторона — числом.') from None
        if not (32 <= width <= 4096 and 32 <= height <= 4096):
            raise ValueError('Размеры холста должны быть от 32 до 4096 пикселей.')
        if not math.isfinite(side) or side <= 0:
            raise ValueError('Сторона должна быть положительным конечным числом.')
        outer = side / (2 * math.sin(math.pi / 5))
        inner = side / (2 * math.tan(math.pi / 5))
        if inner < 1:
            raise ValueError('Сторона слишком мала: вписанный радиус должен быть не меньше 1 пикселя.')
        if not (outer + 2 <= cx < width - outer - 2 and outer + 2 <= cy < height - outer - 2):
            raise ValueError('Окружности не помещаются. Увеличьте холст, измените центр или уменьшите сторону.')
        return width, height, cx, cy, side, inner, outer

    def create_canvas(self):
        try:
            width, height, *_ = self.parameters()
            self.width, self.height = width, height
            if self.canvas is None:
                self.canvas = tk.Canvas(self.drawing_area, background='#e5e7eb', highlightthickness=0)
                horizontal = ttk.Scrollbar(self.drawing_area, orient='horizontal', command=self.canvas.xview)
                vertical = ttk.Scrollbar(self.drawing_area, orient='vertical', command=self.canvas.yview)
                self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
                self.canvas.grid(row=0, column=0, sticky='nsew')
                vertical.grid(row=0, column=1, sticky='ns')
                horizontal.grid(row=1, column=0, sticky='ew')
            self.clear()
        except ValueError as error:
            messagebox.showerror('Параметры', str(error), parent=self)

    def display(self, data):
        ppm = f'P6\n{self.width} {self.height}\n255\n'.encode() + bytes(data)
        self.photo = tk.PhotoImage(data=ppm, format='PPM')
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, self.width, self.height))

    def clear(self):
        if self.canvas is None:
            return
        self.current_data = None
        self.display(b'\xff' * (self.width * self.height * 3))
        self.status.set(f'Холст {self.width} × {self.height}. Выберите алгоритм построения.')

    def drawing_parameters(self):
        if self.canvas is None:
            raise ValueError('Сначала нажмите «Создать холст».')
        params = self.parameters()
        if (self.width, self.height) != params[:2]:
            raise ValueError('Размеры изменены. Нажмите «Создать холст», чтобы применить их.')
        return params

    def render(self, method, params):
        width, height, cx, cy, side, inner, outer = params
        data = bytearray(b'\xff' * (width * height * 3))

        def put(x, y, color):
            if 0 <= x < width and 0 <= y < height:
                offset = 3 * (y * width + x)
                data[offset:offset + 3] = bytes(color)

        if self.show_polygon.get():
            vertices = [(nearest(cx + outer * math.cos(-math.pi / 2 + 2 * math.pi * i / 5)),
                         nearest(cy + outer * math.sin(-math.pi / 2 + 2 * math.pi * i / 5)))
                        for i in range(5)]
            for i in range(5):
                for x, y in line_points(*vertices[i], *vertices[(i + 1) % 5]):
                    put(x, y, (90, 90, 90))
        start = time.perf_counter()
        circles = []
        for radius, color in zip((inner, outer), COLORS):
            # Общие целочисленные входы обеспечивают честное сравнение методов.
            radius = nearest(radius)
            if method == 3:
                points = native_circle(cx, cy, radius, width, height)
            else:
                points = (equation_circle, parametric_circle, bresenham_circle)[method](cx, cy, radius)
            circles.append(points)
            for x, y in points:
                put(x, y, color)
        elapsed = (time.perf_counter() - start) * 1000
        return data, circles, elapsed

    def draw(self, method):
        try:
            params = self.drawing_parameters()
            data, circles, elapsed = self.render(method, params)
            self.display(data)
            self.current_data = data
            self.current_method = method
            self.status.set(f'{METHODS[method]}; a = {params[4]:g}; '
                            f'r = {params[5]:.3f} → {nearest(params[5])} px; '
                            f'R = {params[6]:.3f} → {nearest(params[6])} px; '
                            f'{elapsed:.2f} мс; пикселей окружностей: {len(circles[0]) + len(circles[1])}.')
        except (ValueError, RuntimeError, OSError) as error:
            messagebox.showerror('Построение', str(error), parent=self)

    def load_svg(self):
        filename = filedialog.askopenfilename(parent=self, filetypes=[('SVG', '*.svg')])
        if not filename:
            return
        try:
            if os.path.getsize(filename) > 2_000_000:
                raise ValueError('SVG слишком большой (максимум 2 МБ).')
            root = ET.parse(filename).getroot()
            if root.tag.split('}')[-1] != 'svg':
                raise ValueError('Файл не является SVG.')
            if any(e.get('transform') for e in root.iter()):
                raise ValueError('Используйте SVG без transform: координаты должны быть заданы явно.')

            def number(value):
                if value is None or not re.fullmatch(r'\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:px)?\s*', value):
                    raise ValueError('В SVG нужны числовые размеры и координаты в пикселях.')
                result = float(value.strip().removesuffix('px'))
                if not math.isfinite(result):
                    raise ValueError('Недопустимое число в SVG.')
                return result

            values = {}
            circles = [e for e in root.iter() if e.tag.split('}')[-1] == 'circle']
            polygons = [e for e in root.iter() if e.tag.split('}')[-1] == 'polygon']
            if root.get('data-side'):
                values['side'] = number(root.get('data-side'))
                values['cx'] = number(root.get('data-cx', self.values['cx'].get()))
                values['cy'] = number(root.get('data-cy', self.values['cy'].get()))
            elif polygons:
                coords = [float(v) for v in re.split(r'[\s,]+', polygons[0].get('points', '').strip()) if v]
                if len(coords) == 12 and coords[:2] == coords[-2:]:
                    coords = coords[:-2]
                if len(coords) != 10 or not all(math.isfinite(v) for v in coords):
                    raise ValueError('В polygon должно быть пять вершин.')
                vertices = list(zip(coords[::2], coords[1::2]))
                cx = sum(p[0] for p in vertices) / 5
                cy = sum(p[1] for p in vertices) / 5
                lengths = [math.dist(vertices[i], vertices[(i + 1) % 5]) for i in range(5)]
                side = sum(lengths) / 5
                radius = side / (2 * math.sin(math.pi / 5))
                if side <= 0 or any(abs(v - side) > side * .01 for v in lengths) or any(
                        abs(math.dist((cx, cy), p) - radius) > radius * .01 for p in vertices):
                    raise ValueError('Пятиугольник в SVG должен быть правильным; допуск — 1%.')
                values.update(cx=cx, cy=cy, side=side)
            elif circles:
                circle = max(circles, key=lambda e: number(e.get('r')))
                values.update(cx=number(circle.get('cx', '0')), cy=number(circle.get('cy', '0')),
                              side=2 * number(circle.get('r')) * math.sin(math.pi / 5))
            else:
                raise ValueError('SVG должен содержать polygon с пятью вершинами, описанную circle '
                                 'или атрибуты data-side, data-cx, data-cy корневого svg.')
            if not all(math.isfinite(v) for v in values.values()):
                raise ValueError('Недопустимые числовые значения SVG.')
            self.svg_parameters = values
            self.svg_status.set('SVG найден')
            self.svg_status_label.configure(foreground='#008000')
            self.status.set('SVG загружен: ' + ', '.join(f'{k}={v:g}' for k, v in values.items())
                            + '. Нажмите «Отобразить на холсте».')
        except (ET.ParseError, OSError, ValueError, OverflowError) as error:
            self.svg_parameters = None
            self.svg_status.set('SVG не загружен')
            self.svg_status_label.configure(foreground='#a00000')
            messagebox.showerror('Загрузка SVG', str(error), parent=self)

    def apply_svg(self):
        if self.svg_parameters is None:
            messagebox.showinfo('SVG', 'Сначала загрузите файл SVG.', parent=self)
            return
        if self.canvas is None:
            messagebox.showinfo('SVG', 'Сначала нажмите «Создать».', parent=self)
            return
        previous = {key: value.get() for key, value in self.values.items()}
        try:
            for key, value in self.svg_parameters.items():
                self.values[key].set(f'{value:.12g}' if key == 'side' else str(nearest(value)))
            self.drawing_parameters()
        except ValueError as error:
            for key, value in previous.items():
                self.values[key].set(value)
            messagebox.showerror('Параметры SVG', str(error), parent=self)
            return
        self.draw(self.current_method)

    def save(self, extension):
        if self.current_data is None:
            messagebox.showinfo('Сохранение', 'Сначала постройте изображение.', parent=self)
            return
        filename = filedialog.asksaveasfilename(parent=self, defaultextension='.' + extension,
                                               filetypes=[(extension.upper(), '*.' + extension)])
        if not filename:
            return
        data = self.current_data
        try:
            with open(filename, 'wb') as output:
                if extension == 'bmp':
                    stride = (self.width * 3 + 3) & ~3
                    size = stride * self.height
                    output.write(struct.pack('<2sIHHI', b'BM', 54 + size, 0, 0, 54))
                    output.write(struct.pack('<IiiHHIIiiII', 40, self.width, self.height,
                                             1, 24, 0, size, 2835, 2835, 0, 0))
                    for y in range(self.height - 1, -1, -1):
                        row = data[y * self.width * 3:(y + 1) * self.width * 3]
                        bgr = bytearray(len(row))
                        bgr[0::3], bgr[1::3], bgr[2::3] = row[2::3], row[1::3], row[0::3]
                        output.write(bgr)
                        output.write(b'\0' * (stride - len(row)))
                else:
                    output.write(f'P4\n{self.width} {self.height}\n'.encode())
                    for y in range(self.height):
                        row = bytearray((self.width + 7) // 8)
                        for x in range(self.width):
                            offset = 3 * (y * self.width + x)
                            if data[offset:offset + 3] != b'\xff\xff\xff':
                                row[x // 8] |= 1 << (7 - x % 8)
                        output.write(row)
            self.status.set(f'Сохранено: {filename}')
        except OSError as error:
            messagebox.showerror('Сохранение', str(error), parent=self)


if __name__ == '__main__':
    Application().mainloop()
