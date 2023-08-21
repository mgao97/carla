import glob
import os
import sys
import threading
from queue import Queue
from queue import Empty
import time
import random

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla


def capture_image(image, camera_index, camera_folder):
    image.save_to_disk(os.path.join(camera_folder, f'image_{camera_index}_{image.frame}.png'))


# def sensor_callback(sensor_data, sensor_queue, sensor_name, camera_transform, camera_folder):
#     # Save image and record position
#     if sensor_name.startswith("camera"):
#         camera_index = int(sensor_name.split("_")[1])
#         capture_image(sensor_data, camera_index, camera_folder)
#         record_camera_position(camera_transform, camera_folder)
    
#     sensor_queue.put((sensor_data.frame, sensor_name, camera_transform))

# Inside the sensor_callback function
def sensor_callback(sensor_data, sensor_queues, sensor_name, camera_transform, camera_folder):
    print(f"Received data from {sensor_name}, Frame: {sensor_data.frame}")
    # Save image and record position
    if sensor_name.startswith("camera"):
        camera_index = int(sensor_name.split("_")[1])
        capture_image(sensor_data, camera_index, camera_folder)
        record_camera_position(camera_transform, camera_folder)

    # Put data into the corresponding queue based on sensor name
    sensor_queues[sensor_name].put((sensor_data.frame, sensor_name, camera_transform))

def record_camera_position(camera_transform, camera_folder):
    camera_position = camera_transform.location
    camera_rotation = camera_transform.rotation
    position_file_path = os.path.join(camera_folder, 'position.txt')

    if not os.path.exists(position_file_path):
        with open(position_file_path, 'w') as position_file:
            position_file.write('Camera Position and Rotation Records:\n')

    with open(position_file_path, 'a') as position_file:
        position_file.write(f'Position: {camera_position}, Rotation: {camera_rotation}\n')

def spawn_vehicles(world, num_vehicles, speed):
    blueprint_library = world.get_blueprint_library()
    spawn_points = world.get_map().get_spawn_points()
    vehicles = []

    for i in range(1, num_vehicles+1):
        blueprint = random.choice(blueprint_library.filter('vehicle.*'))
        transform = random.choice(spawn_points)

        while True:
            try:
                vehicle = world.spawn_actor(blueprint, transform)
                vehicle.set_target_velocity(carla.Vector3D(speed, 0, 0))
                break
            except RuntimeError:
                transform = random.choice(spawn_points)

        vehicles.append(vehicle)

    return vehicles

# Inside the camera_thread function

# Inside the camera_thread function

def camera_thread(camera, camera_transform, camera_folder):
    time_interval = 1.0 / 10.0  # Calculate time interval for 30 fps

    # Set exposure settings at the beginning
    camera.exposure_compensation = 0.5
    camera.exposure_max_bright = 0.5

    while True:
        start_time = time.time()

        # Set other camera attributes for better image quality
        camera.sensor_tick = 0.1  # Adjust the sensor tick rate as needed
        #camera.image_size_x = 1280  # Adjust image resolution as needed
        #camera.image_size_y = 720
        camera.image_size_x = 800  # Adjust image resolution as needed
        camera.image_size_y = 600
        camera.focal_length = 4.0  # Adjust the focal length for sharper images
        camera.aperture = 2.0  # Adjust the aperture for better depth of field

        # No need to capture image here, as it's done through the callback
        elapsed_time = time.time() - start_time
        if elapsed_time < time_interval:
            time.sleep(time_interval - elapsed_time)



def main():
    client = carla.Client('localhost', 2000)
    client.set_timeout(10.0)
    world = client.get_world()

    try:
        original_settings = world.get_settings()
        settings = world.get_settings()

        settings.fixed_delta_seconds = 0.2
        settings.synchronous_mode = True
        world.apply_settings(settings)

        

        blueprint_library = world.get_blueprint_library()
        cam_bp = blueprint_library.find('sensor.camera.rgb')

        num_vehicles = 10
        vehicles = spawn_vehicles(world, num_vehicles, 10)
        
        
        # Create a dictionary to hold separate sensor queues for each camera
        sensor_queues = dict()
        for i in range(1,num_vehicles+1):
            sensor_queues[f"camera_{i}"] = Queue()
            


        cameras = []
        for i, vehicle in enumerate(vehicles):
            print('*************vehicle info.***********************')
            print(i, vehicle)
            print('*************************************************')
            camera_transform = carla.Transform(carla.Location(x=1.5, z=2.5), carla.Rotation(yaw=0))
            camera = world.spawn_actor(cam_bp, camera_transform, attach_to=vehicle)
            camera_folder = f'images/{time.strftime("%m-%d-%H-%M")}_10fps_wet/camera_{i+1}_folder'
            os.makedirs(camera_folder, exist_ok=True)
            
            
            print('*************camera queue***********************')
            print(sensor_queues)
            print('*************************************************')
            
            camera.listen(
                lambda data, camera_transform=camera_transform, sensor_queue=sensor_queues[f"camera_{i+1}"], camera_folder=camera_folder: sensor_callback(data, sensor_queues, f"camera_{i+1}", camera_transform, camera_folder)
            )
            cameras.append((camera, camera_transform, camera_folder))
        
            

        
        camera_threads = []
        for camera, camera_transform, camera_folder in cameras:
            thread = threading.Thread(target=camera_thread, args=(camera, camera_transform, camera_folder))
            camera_threads.append(thread)
            thread.start()

        while True:
            world.tick()
            w_frame = world.get_snapshot().frame
            print("\nWorld's frame: %d" % w_frame)

            try:
                for i, (s_name, camera_transform, _) in enumerate(cameras):
                    s_frame, _, _ = sensor_queues[f'camera_{i+1}'].get(True, 1.0)
                    print("    Frame: %d   Sensor: %s" % (s_frame, f'camera_{i+1}'))
                    sensor_folder = next((folder for _, _, folder in cameras if folder.startswith(f'camera_{i+1}')), None)
                    if sensor_folder is not None:
                        record_camera_position(camera_transform, sensor_folder)

            except Empty:
                print("    Some of the sensor information is missed")

        #This code should ensure that data is correctly retrieved and processed for all cameras. Each camera will have its own dedicated queue, preventing the issue of data being consumed by one camera and not the others.

            # try:
            #     for _ in range(len(cameras)):
            #         s_frame, s_name, camera_transform = sensor_queue.get(True, 2.0)
            #         print("    Frame: %d   Sensor: %s" % (s_frame, s_name))
            #         sensor_folder = next((folder for _, _, folder in cameras if folder.startswith(s_name)), None)
            #         if sensor_folder is not None:
            #             record_camera_position(camera_transform, sensor_folder)

            # except Empty:
            #     print("    Some of the sensor information is missed")
        for camera, _, _ in cameras:
            camera.destroy()

    finally:
        world.apply_settings(original_settings)
        client.apply_batch([carla.command.DestroyActor(actor) for actor in world.get_actors()])
        

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(' - Exited by user.')
