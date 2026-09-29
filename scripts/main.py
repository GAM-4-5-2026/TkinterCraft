import tkinter as tk
from objects import *
import random as rand

cols = 128
rows = 72

class TextGridApp:
    def __init__(self, root):
        self.root = root
        self.root.title("144p Text Grid")
        self.root.geometry("1200x700")

        self.text_area = tk.Text(
            root, 
            font=("Courier", 5),  
            bg="black", 
            fg="lightgreen", 
            wrap="none",
            bd=0,
            highlightthickness=0
        )
        
        self.text_area.pack(fill="both", expand = True)

        self.grid_data = [
            [chr(rand.randint(65, 90)) for _ in range(cols)]
            for _ in range(rows)
            ]

        self.render_grid()

    def render_grid(self):
        full_text = "\n".join("".join(row) for row in self.grid_data)

        self.text_area.config(state="normal")
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", full_text)
        self.text_area.config(state="disabled")

    def update_cell(self, row, col, new_letter):
        if 0 <= row < ROWS and 0 <= col < COLS:
            self.grid_data[row][col] = new_letter
            self.render_grid()



def on_keypress(event):
    print(f"Key presed: char='{event.char}', keysym='{event.keysym}'")


if __name__ == "__main__":
    root = tk.Tk()
    app = TextGridApp(root)
    root.mainloop()
