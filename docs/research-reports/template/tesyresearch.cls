\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{tesyresearch}[2026/09/27 v1.0.0 Tesy reports]
\LoadClass[11pt,a4paper]{article}
\RequirePackage{iftex}
\ifLuaTeX\else\ClassError{tesyresearch}{LuaLaTeX required}{}\fi
\RequirePackage[margin=21mm,top=20mm,bottom=23mm,headheight=14pt,headsep=7mm]{geometry}
\RequirePackage{fontspec}
\setmainfont{Latin Modern Roman}
\setsansfont{Latin Modern Sans}
\setmonofont{Latin Modern Mono}[Scale=MatchLowercase]
\RequirePackage[english,portuguese]{babel}
\RequirePackage{microtype,booktabs,tabularx,longtable,array,siunitx,graphicx,xcolor}
\sisetup{output-decimal-marker={,},group-separator={\,},group-minimum-digits=5}
\definecolor{TesyAccent}{HTML}{244A61}
\definecolor{TesyMuted}{HTML}{59636A}
\RequirePackage{pgfplots}
\pgfplotsset{compat=1.18,every axis/.append style={font=\small,grid=major,width=.96\linewidth,height=6cm,legend style={font=\footnotesize},tick label style={font=\footnotesize}}}
\pgfkeys{/pgf/number format/.cd,use comma,1000 sep={\,}}
\RequirePackage[most]{tcolorbox}
\RequirePackage{titlesec}
\titleformat{\section}{\sffamily\Large\bfseries\color{TesyAccent}}{\thesection}{.7em}{}
\titleformat{\subsection}{\sffamily\large\bfseries}{\thesubsection}{.6em}{}
\titlespacing*{\section}{0pt}{15pt}{7pt}
\titlespacing*{\subsection}{0pt}{10pt}{5pt}
\RequirePackage{caption}
\captionsetup{font=small,labelfont=bf,skip=6pt}
\RequirePackage{fancyhdr,xurl}
\RequirePackage[unicode,pdfencoding=auto]{hyperref}
\hypersetup{colorlinks=true,linkcolor=TesyAccent,urlcolor=TesyAccent,citecolor=TesyAccent}
\RequirePackage[nameinlink,noabbrev]{cleveref}
\RequirePackage[backend=biber,style=numeric,sorting=none]{biblatex}
\RequirePackage{etoolbox,needspace}
\AfterEndEnvironment{tabularx}{\par\smallskip}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt plus 1pt}
\renewcommand{\arraystretch}{1.2}
\setlength{\tabcolsep}{5pt}
\linespread{1.06}
\clubpenalty=10000\widowpenalty=10000\emergencystretch=1.5em
\pdfvariable suppressoptionalinfo 767
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\sffamily\scriptsize\color{TesyMuted}TESY / INVESTIGAÇÃO EM SISTEMAS}
\fancyhead[R]{\sffamily\scriptsize\color{TesyMuted}\ReportID}
\fancyfoot[L]{\sffamily\scriptsize\color{TesyMuted}v\ReportVersion\quad /\quad fontes \texttt{\ReportDigest}}
\fancyfoot[R]{\sffamily\small\thepage}
\renewcommand{\headrulewidth}{.25pt}
\newcolumntype{Y}{>{\raggedright\arraybackslash}X}
\newcommand{\ReportMasthead}{%
 {\sffamily\bfseries\color{TesyAccent}\fontsize{13}{15}\selectfont TESY / RESEARCH REPORT\par}\vspace{3mm}
 {\sffamily\bfseries\fontsize{25}{29}\selectfont\ReportTitle\par}\vspace{2mm}
 {\large\ReportSubtitle\par}
 \ifdefempty{\ReportAuthor}{}{{\small\ReportAuthor\par}}
 {\small\sffamily\color{TesyMuted}\ReportID\quad|\quad\ReportDate\quad|\quad v\ReportVersion\par}
 \begin{tcolorbox}[colback=TesyAccent!4,colframe=TesyAccent,boxrule=.5pt,arc=0pt,left=3mm,right=3mm,top=2mm,bottom=2mm]
 {\sffamily\scriptsize ESTADO CIENTÍFICO DA FONTE}\par{\sffamily\bfseries\ReportState}\par{\small\ReportScope}
 \end{tcolorbox}}
\newenvironment{FindingBox}[1]{\begin{tcolorbox}[enhanced,breakable,colback=TesyAccent!3,colframe=TesyAccent!50,boxrule=.4pt,arc=0pt,title={#1},fonttitle=\sffamily\bfseries,coltitle=black,colbacktitle=TesyAccent!8]}{\end{tcolorbox}}
\newcommand{\EvidenceEntry}[5]{\Needspace{23mm}\par\medskip\hypertarget{ev:#1}{}%
 {\sffamily\bfseries\small #1}\quad {\small\href{#5}{Fonte congelada}}\par
 {\footnotesize\ttfamily\detokenize{#2}\par}
 {\scriptsize Commit: \nolinkurl{#3}\par SHA-256: \nolinkurl{#4}\par}}
\AtBeginDocument{%
 \ifdefstring{\ReportLanguage}{en}{\selectlanguage{english}\sisetup{output-decimal-marker={.}}\pgfkeys{/pgf/number format/.cd,use period}}{\selectlanguage{portuguese}}
 \hypersetup{pdftitle={\ReportTitle},pdfsubject={\ReportID\space v\ReportVersion},pdfauthor={Tesy}}
 \ifdefempty{\ReportAuthor}{}{\hypersetup{pdfauthor={\ReportAuthor}}}}
\endinput
