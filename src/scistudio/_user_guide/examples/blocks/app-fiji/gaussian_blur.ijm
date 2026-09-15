// Fiji/ImageJ macro: Gaussian-blur every image in the exchange folder.
//
// SciStudio launches Fiji with the exchange-folder path as the macro argument.
// Inputs are in  <exchange>/inputs/ , outputs go in <exchange>/outputs/ .
// SciStudio waits for files matching the block's output_patterns ("*.tif").

exchange = getArgument();
inputs  = exchange + "/inputs/";
outputs = exchange + "/outputs/";
File.makeDirectory(outputs);

list = getFileList(inputs);
for (i = 0; i < list.length; i++) {
    name = list[i];
    if (endsWith(name, "/")) continue;           // skip sub-folders

    open(inputs + name);
    run("Gaussian Blur...", "sigma=2");
    saveAs("Tiff", outputs + "blurred_" + name);
    close();
}
