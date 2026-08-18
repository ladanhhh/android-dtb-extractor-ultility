
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import struct, re

MAGIC = 0xD00DFEED

def be32(b, o):
    return struct.unpack_from(">I", b, o)[0]

def parse_dtb(data):
    if len(data) < 40 or be32(data,0) != MAGIC:
        raise ValueError("Not a valid DTB/FDT file.")
    totalsize = be32(data,4)
    off_struct = be32(data,8)
    off_strings = be32(data,12)
    size_struct = be32(data,36)
    size_strings = be32(data,32)
    if totalsize > len(data):
        raise ValueError("DTB is truncated.")
    strings = data[off_strings:off_strings+size_strings]
    s = data[off_struct:off_struct+size_struct]
    p=0; depth=0; lines=[]
    while p+4 <= len(s):
        token=be32(s,p); p+=4
        if token==1: # BEGIN_NODE
            end=s.find(b'\0',p)
            if end<0: raise ValueError("Bad node name")
            name=s[p:end].decode('utf-8','replace') or "/"
            p=(end+4)&~3
            lines.append(("node",depth,name))
            depth+=1
        elif token==2: # END_NODE
            depth=max(0,depth-1)
        elif token==3: # PROP
            if p+8>len(s): raise ValueError("Bad property")
            ln=be32(s,p); no=be32(s,p+4); p+=8
            val=s[p:p+ln]; p=(p+ln+3)&~3
            end=strings.find(b'\0',no)
            name=strings[no:end].decode('utf-8','replace') if end>=0 else f"prop@{no:x}"
            # Friendly representation
            if ln==0: v="<empty>"
            elif name in ("compatible","model","status","bootargs") or all(32<=x<127 or x in (9,10,13) for x in val.rstrip(b'\0')):
                v=val.rstrip(b'\0').decode('utf-8','replace').replace('\0',' | ')
            elif ln%4==0:
                vals=[be32(val,i) for i in range(0,ln,4)]
                v="<" + " ".join(hex(x) for x in vals) + ">"
            else:
                v="["+" ".join(f"{x:02x}" for x in val)+"]"
            lines.append(("prop",depth,name,v))
        elif token==4: # NOP
            pass
        elif token==9: # END
            break
        else:
            raise ValueError(f"Unknown FDT token 0x{token:x} at 0x{p-4:x}")
    return lines, totalsize, be32(data,16), be32(data,20)

def main():
    root=tk.Tk()
    root.title("DTB Explorer - Hi3798MV310")
    root.geometry("1050x700")
    root.minsize(800,500)
    current=None
    text=None

    top=ttk.Frame(root,padding=8); top.pack(fill="x")
    ttk.Button(top,text="Open DTB",command=lambda:open_file()).pack(side="left")
    ttk.Button(top,text="Export DTS-like text",command=lambda:export_text()).pack(side="left",padx=6)
    ttk.Button(top,text="Save raw DTB",command=lambda:save_raw()).pack(side="left")
    info=ttk.Label(top,text="No file loaded"); info.pack(side="right")

    frame=ttk.Frame(root); frame.pack(fill="both",expand=True,padx=8,pady=(0,8))
    tree=ttk.Treeview(frame,columns=("value",),show="tree headings")
    tree.heading("#0",text="Device Tree")
    tree.heading("value",text="Value")
    tree.column("#0",width=430)
    tree.column("value",width=560)
    ys=ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
    xs=ttk.Scrollbar(frame,orient="horizontal",command=tree.xview)
    tree.configure(yscrollcommand=ys.set,xscrollcommand=xs.set)
    tree.grid(row=0,column=0,sticky="nsew"); ys.grid(row=0,column=1,sticky="ns"); xs.grid(row=1,column=0,sticky="ew")
    frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)

    def load(path):
        nonlocal current
        data=Path(path).read_bytes()
        lines,total,ver,last= parse_dtb(data)
        tree.delete(*tree.get_children())
        stack=[]
        for typ,depth,name,*rest in lines:
            while len(stack)>depth: stack.pop()
            if typ=="node":
                parent=stack[-1] if stack else ""
                iid=tree.insert(parent,"end",text=name,values=("",))
                stack.append(iid)
            else:
                parent=stack[-1] if stack else ""
                tree.insert(parent,"end",text=name,values=(rest[0],))
        current=data
        info.config(text=f"{Path(path).name} | {len(data):,} bytes | FDT v{ver}")
    def open_file():
        p=filedialog.askopenfilename(filetypes=[("Device Tree Blob","*.dtb *.dtbo *.img"),("All files","*.*")])
        if p:
            try: load(p)
            except Exception as e: messagebox.showerror("DTB error",str(e))
    def export_text():
        if current is None: return
        p=filedialog.asksaveasfilename(defaultextension=".dts",filetypes=[("DTS text","*.dts")])
        if not p:return
        lines,total,ver,last=parse_dtb(current)
        out=["/dts-v1/;","", "/ {"] 
        def indent(n): return "    "*n
        for typ,depth,name,*rest in lines:
            if typ=="node":
                if name=="/": continue
                out.append(indent(depth)+name+" {")
            else:
                out.append(indent(depth)+name+" = "+rest[0]+";")
        # Close based on node depths
        # Rebuild more accurately
        out=["/dts-v1/;","", "/ {"]
        for typ,depth,name,*rest in lines:
            if typ=="node":
                if name!="/": out.append(indent(depth)+name+" {")
            else:
                out.append(indent(depth)+name+" = "+rest[0]+";")
        # close all nodes using a simple depth change reconstruction
        # Use a second pass over parsed lines
        out=["/dts-v1/;",""]
        for i,(typ,depth,name,*rest) in enumerate(lines):
            if typ=="node":
                if name=="/": out.append("/ {")
                else: out.append(indent(depth)+name+" {")
                continue
            out.append(indent(depth)+name+" = "+rest[0]+";")
            # close nodes before next node/property at shallower depth
            next_depth=depth
            if i+1<len(lines): next_depth=lines[i+1][1]
            if next_depth<depth:
                for d in range(depth,next_depth,-1): out.append(indent(d-1)+"};")
        # Ensure root close
        out.append("};")
        Path(p).write_text("\n".join(out),encoding="utf-8")
        messagebox.showinfo("Saved",f"Saved {p}")
    def save_raw():
        if current is None:return
        p=filedialog.asksaveasfilename(defaultextension=".dtb",filetypes=[("DTB","*.dtb")])
        if p: Path(p).write_bytes(current)
    root.mainloop()
main()
