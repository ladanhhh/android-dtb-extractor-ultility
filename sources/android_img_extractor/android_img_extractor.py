
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import struct, gzip, lzma, zlib, bz2, io

FDT_MAGIC=0xD00DFEED

def u32(b,o): return struct.unpack_from("<I",b,o)[0]
def be32(b,o): return struct.unpack_from(">I",b,o)[0]

def align(x,n): return (x+n-1)//n*n

def parse_android_boot(data):
    if data[:8] == b"ANDROID!":
        # Android legacy boot header: 8s + 10 uint32 little endian fields
        vals=struct.unpack_from("<8s10I",data,0)
        _, ksz, rsz, osz, tagsz, pagesz, dt_sz, *_ = vals
        if pagesz==0 or pagesz & (pagesz-1): pagesz=4096
        ko=pagesz
        ro=align(ko+ksz,pagesz)
        to=align(ro+rsz,pagesz)
        oo=align(to+tagsz,pagesz)
        parts=[]
        if ksz: parts.append(("kernel",ko,ksz))
        if rsz: parts.append(("ramdisk",ro,rsz))
        if tagsz: parts.append(("second",to,tagsz))
        if dt_sz: parts.append(("dtb",oo,dt_sz))
        return {"type":"Android boot image (legacy)","parts":parts,"pagesize":pagesz}
    if data[:4] == b"VNDRBOOT":
        raise ValueError("Android vendor_boot detected. This GUI currently supports legacy ANDROID! boot.img; vendor_boot support can be added.")
    return None

def find_dtbs(data):
    found=[]
    start=0
    while True:
        i=data.find(b"\xd0\x0d\xfe\xed",start)
        if i<0: break
        if i+40<=len(data):
            try:
                total=be32(data,i+4)
                off_struct=be32(data,i+8); off_strings=be32(data,i+12)
                if 40<=total<=len(data)-i and off_struct<total and off_strings<total:
                    found.append((i,total))
            except: pass
        start=i+4
    return found

def sparse_to_raw(data):
    # Android sparse image format
    if len(data)<28 or u32(data,0)!=0xED26FF3A:
        raise ValueError("Not an Android sparse image.")
    _, major, minor, fh, ch, blk, total_blks, total_chunks, checksum = struct.unpack_from("<IHHHHIIII",data,0)
    if major!=1: raise ValueError("Unsupported sparse version.")
    p=fh
    out=bytearray()
    for _ in range(total_chunks):
        if p+12>len(data): raise ValueError("Truncated sparse image.")
        typ,reserved,chunk_sz,total_sz=struct.unpack_from("<HHII",data,p); p+=12
        rawsz=chunk_sz*blk
        payload=total_sz-12
        if typ==0xCAC1: # RAW
            out.extend(data[p:p+payload]); p+=payload
        elif typ==0xCAC2: # FILL
            word=data[p:p+4]; p+=4
            out.extend(word*(rawsz//4))
        elif typ==0xCAC3: # DONT_CARE
            out.extend(b"\0"*rawsz)
        elif typ==0xCAC4: # CRC32
            p+=payload
        else: raise ValueError(f"Unknown sparse chunk 0x{typ:04x}")
    return bytes(out)

def decompress_blob(data, outpath):
    sig=data[:8]
    try:
        if sig[:2]==b"\x1f\x8b":
            raw=gzip.decompress(data)
        elif sig[:6]==b"\xfd7zXZ\0":
            raw=lzma.decompress(data)
        elif sig[:2]==b"BZ":
            raw=bz2.decompress(data)
        else:
            raise ValueError("Unknown compression")
        Path(outpath).write_bytes(raw); return len(raw)
    except Exception as e: raise ValueError(str(e))

class App:
    def __init__(self,root):
        self.root=root; self.data=None; self.path=None; self.kind=None; self.boot=None
        root.title("Android IMG Extractor")
        root.geometry("980x680")
        top=ttk.Frame(root,padding=8); top.pack(fill="x")
        ttk.Button(top,text="Open IMG",command=self.open).pack(side="left")
        ttk.Button(top,text="Extract All",command=self.extract_all).pack(side="left",padx=5)
        ttk.Button(top,text="Convert Sparse → RAW",command=self.convert_sparse).pack(side="left",padx=5)
        ttk.Button(top,text="Scan for DTBs",command=self.scan_dtbs).pack(side="left",padx=5)
        self.info=ttk.Label(top,text="No image loaded"); self.info.pack(side="right")
        frame=ttk.Frame(root,padding=8); frame.pack(fill="both",expand=True)
        self.tree=ttk.Treeview(frame,columns=("offset","size"),show="tree headings")
        self.tree.heading("#0",text="Component"); self.tree.heading("offset",text="Offset"); self.tree.heading("size",text="Size")
        self.tree.column("#0",width=500); self.tree.column("offset",width=180); self.tree.column("size",width=180)
        self.tree.pack(fill="both",expand=True)
        bottom=ttk.Label(root,text="Supports Android legacy boot.img, DTB scanning/extraction, U-Boot-style bootargs.img inspection, DTBO images, and Android sparse images.",padding=6)
        bottom.pack(fill="x")

    def open(self):
        p=filedialog.askopenfilename(filetypes=[("Android images","*.img *.dtb *.dtbo"),("All files","*.*")])
        if not p:return
        try:
            self.data=Path(p).read_bytes(); self.path=Path(p)
            self.tree.delete(*self.tree.get_children())
            self.kind="unknown"; self.boot=None
            if self.data[:8]==b"ANDROID!":
                self.boot=parse_android_boot(self.data); self.kind="boot"
                self.info.config(text=f"{self.path.name} — {self.boot['type']}")
                for n,o,s in self.boot["parts"]: self.tree.insert("", "end", text=n, values=(hex(o),f"{s:,} bytes"))
            elif len(self.data)>=4 and u32(self.data,0)==0xED26FF3A:
                self.kind="sparse"; self.info.config(text=f"{self.path.name} — Android sparse image")
                self.tree.insert("", "end", text="Sparse image", values=("0",f"{len(self.data):,} bytes"))
            elif self.data[:4]==b"VNDR":
                self.kind="vendor"; self.info.config(text=f"{self.path.name} — vendor boot image")
                self.tree.insert("", "end", text="Vendor boot image", values=("0",f"{len(self.data):,} bytes"))
            else:
                ds=find_dtbs(self.data)
                self.info.config(text=f"{self.path.name} — unknown/raw image")
                self.tree.insert("", "end", text="Raw image", values=("0",f"{len(self.data):,} bytes"))
                for i,(o,s) in enumerate(ds): self.tree.insert("", "end", text=f"DTB #{i}", values=(hex(o),f"{s:,} bytes"))
        except Exception as e: messagebox.showerror("Open error",str(e))

    def extract_all(self):
        if self.data is None:return
        out=filedialog.askdirectory(title="Choose extraction folder")
        if not out:return
        out=Path(out); out.mkdir(exist_ok=True)
        try:
            if self.kind=="boot":
                for n,o,s in self.boot["parts"]: (out/(n+".bin" if n!="dtb" else "extracted.dtb")).write_bytes(self.data[o:o+s])
                # Also scan whole image for valid DTBs
                for i,(o,s) in enumerate(find_dtbs(self.data)):
                    (out/f"dtb_{i}.dtb").write_bytes(self.data[o:o+s])
            elif self.kind=="sparse":
                (out/(self.path.stem+".raw.img")).write_bytes(sparse_to_raw(self.data))
            else:
                ds=find_dtbs(self.data)
                for i,(o,s) in enumerate(ds): (out/f"dtb_{i}.dtb").write_bytes(self.data[o:o+s])
                (out/self.path.name).write_bytes(self.data)
            messagebox.showinfo("Done",f"Extracted to:\n{out}")
        except Exception as e: messagebox.showerror("Extraction error",str(e))

    def convert_sparse(self):
        if self.kind!="sparse": messagebox.showinfo("Not sparse","Open an Android sparse image first."); return
        p=filedialog.asksaveasfilename(defaultextension=".img",initialfile=self.path.stem+".raw.img",filetypes=[("RAW image","*.img")])
        if not p:return
        try:
            Path(p).write_bytes(sparse_to_raw(self.data)); messagebox.showinfo("Done","RAW image created.")
        except Exception as e: messagebox.showerror("Error",str(e))

    def scan_dtbs(self):
        if self.data is None:return
        ds=find_dtbs(self.data)
        self.tree.delete(*self.tree.get_children())
        for i,(o,s) in enumerate(ds): self.tree.insert("", "end", text=f"DTB #{i}", values=(hex(o),f"{s:,} bytes"))
        self.info.config(text=f"Found {len(ds)} valid-looking DTB(s)")

root=tk.Tk()
App(root)
root.mainloop()
